#include "enpiro_store.h"

#include <sqlite3.h>

#include <limits.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#define EP_ENVIRONMENT_ATOM_COUNT 5U

struct ep_store {
    sqlite3 *database;
};

static enum ep_status ep_sqlite_status(int result) {
    switch (result & 0xff) {
    case SQLITE_CONSTRAINT:
        return EP_CONFLICT;
    case SQLITE_CORRUPT:
    case SQLITE_NOTADB:
        return EP_CORRUPT;
    case SQLITE_CANTOPEN:
    case SQLITE_IOERR:
    case SQLITE_FULL:
    case SQLITE_READONLY:
        return EP_STORAGE;
    default:
        return EP_INTERNAL;
    }
}

static int ep_bind_blob(sqlite3_stmt *statement, int parameter,
                        const struct ep_blob *blob) {
    if (blob == NULL || blob->length > (size_t)INT_MAX) {
        return SQLITE_MISUSE;
    }
    return sqlite3_bind_blob(statement, parameter, blob->data,
                             (int)blob->length, SQLITE_TRANSIENT);
}

static enum ep_status ep_initialize_schema(sqlite3 *database) {
    static const char schema[] =
        "PRAGMA foreign_keys = ON;"
        "CREATE TABLE IF NOT EXISTS core_term ("
        "id INTEGER PRIMARY KEY"
        ");"
        "CREATE TABLE IF NOT EXISTS core_symbol ("
        "id INTEGER PRIMARY KEY,"
        "symbol BLOB NOT NULL UNIQUE"
        ");"
        "CREATE TABLE IF NOT EXISTS core_termsymbol ("
        "id INTEGER PRIMARY KEY,"
        "\"order\" INTEGER NOT NULL,"
        "symbol_id INTEGER NOT NULL REFERENCES core_symbol(id) ON DELETE RESTRICT,"
        "term_id INTEGER NOT NULL REFERENCES core_term(id) ON DELETE CASCADE,"
        "UNIQUE(term_id, \"order\")"
        ");"
        "CREATE INDEX IF NOT EXISTS core_ts_ord_sym_term_idx "
        "ON core_termsymbol(\"order\", symbol_id, term_id);";

    return sqlite3_exec(database, schema, NULL, NULL, NULL) == SQLITE_OK
        ? EP_OK
        : ep_sqlite_status(sqlite3_extended_errcode(database));
}

enum ep_status ep_store_open(const char *path, struct ep_store **out) {
    struct ep_store *store;
    int result;

    if (path == NULL || out == NULL || path[0] == '\0') {
        return EP_INVALID_INPUT;
    }
    *out = NULL;
    store = calloc(1U, sizeof(*store));
    if (store == NULL) {
        return EP_INTERNAL;
    }
    result = sqlite3_open_v2(path, &store->database,
                             SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE,
                             NULL);
    if (result != SQLITE_OK) {
        enum ep_status status = ep_sqlite_status(result);
        sqlite3_close(store->database);
        free(store);
        return status;
    }
    (void)sqlite3_extended_result_codes(store->database, 1);
    if (sqlite3_exec(store->database, "PRAGMA foreign_keys = ON;", NULL, NULL,
                     NULL) != SQLITE_OK ||
        ep_initialize_schema(store->database) != EP_OK) {
        sqlite3_close(store->database);
        free(store);
        return EP_STORAGE;
    }
    *out = store;
    return EP_OK;
}

void ep_store_close(struct ep_store *store) {
    if (store == NULL) {
        return;
    }
    sqlite3_close(store->database);
    free(store);
}

static enum ep_status ep_find_symbol(sqlite3 *database,
                                     const struct ep_blob *value,
                                     int64_t *symbol_id) {
    static const char query[] =
        "SELECT id FROM core_symbol WHERE symbol = ?1 LIMIT 1;";
    sqlite3_stmt *statement = NULL;
    int result;

    result = sqlite3_prepare_v2(database, query, -1, &statement, NULL);
    if (result != SQLITE_OK) {
        return ep_sqlite_status(result);
    }
    result = ep_bind_blob(statement, 1, value);
    if (result == SQLITE_OK) {
        result = sqlite3_step(statement);
    }
    if (result == SQLITE_ROW) {
        *symbol_id = sqlite3_column_int64(statement, 0);
        sqlite3_finalize(statement);
        return EP_OK;
    }
    sqlite3_finalize(statement);
    return result == SQLITE_DONE ? EP_NOT_FOUND : ep_sqlite_status(result);
}

static enum ep_status ep_resolve_symbol(sqlite3 *database,
                                        const struct ep_blob *value,
                                        int64_t *symbol_id) {
    enum ep_status status = ep_find_symbol(database, value, symbol_id);
    sqlite3_stmt *statement = NULL;
    int result;

    if (status == EP_OK) {
        return EP_OK;
    }
    if (status != EP_NOT_FOUND) {
        return status;
    }
    result = sqlite3_prepare_v2(
        database,
        "INSERT INTO core_symbol(symbol) VALUES (?1);",
        -1, &statement, NULL);
    if (result == SQLITE_OK) {
        result = ep_bind_blob(statement, 1, value);
    }
    if (result == SQLITE_OK) {
        result = sqlite3_step(statement);
    }
    sqlite3_finalize(statement);
    if (result == SQLITE_DONE) {
        *symbol_id = sqlite3_last_insert_rowid(database);
        return EP_OK;
    }
    if ((result & 0xff) == SQLITE_CONSTRAINT) {
        return ep_find_symbol(database, value, symbol_id);
    }
    return ep_sqlite_status(result);
}

static enum ep_status ep_find_exact_term(sqlite3 *database,
                                         const int64_t *symbol_ids,
                                         size_t atom_count,
                                         int64_t *term_id) {
    sqlite3_stmt *terms = NULL;
    sqlite3_stmt *relations = NULL;
    int result;

    result = sqlite3_prepare_v2(
        database,
        "SELECT id FROM core_term WHERE "
        "(SELECT count(*) FROM core_termsymbol WHERE term_id=core_term.id)=?1 "
        "ORDER BY id;",
        -1, &terms, NULL);
    if (result != SQLITE_OK) {
        return ep_sqlite_status(result);
    }
    result = sqlite3_prepare_v2(
        database,
        "SELECT symbol_id FROM core_termsymbol WHERE term_id=?1 "
        "ORDER BY \"order\";",
        -1, &relations, NULL);
    if (result != SQLITE_OK) {
        sqlite3_finalize(terms);
        return ep_sqlite_status(result);
    }
    sqlite3_bind_int64(terms, 1, (sqlite3_int64)atom_count);
    while ((result = sqlite3_step(terms)) == SQLITE_ROW) {
        bool matches = true;
        size_t index = 0U;
        sqlite3_bind_int64(relations, 1, sqlite3_column_int64(terms, 0));
        while (matches && (result = sqlite3_step(relations)) == SQLITE_ROW) {
            if (index >= atom_count ||
                sqlite3_column_int64(relations, 0) != symbol_ids[index]) {
                matches = false;
            }
            ++index;
        }
        if (result != SQLITE_DONE || index != atom_count) {
            matches = false;
        }
        sqlite3_reset(relations);
        sqlite3_clear_bindings(relations);
        if (matches) {
            *term_id = sqlite3_column_int64(terms, 0);
            sqlite3_finalize(relations);
            sqlite3_finalize(terms);
            return EP_OK;
        }
    }
    sqlite3_finalize(relations);
    sqlite3_finalize(terms);
    if (result == SQLITE_DONE) {
        return EP_NOT_FOUND;
    }
    return ep_sqlite_status(result);
}

enum ep_status ep_store_resolve_term(struct ep_store *store,
                                     const struct ep_blob *atoms,
                                     size_t atom_count,
                                     int64_t *term_id) {
    sqlite3_stmt *statement = NULL;
    int64_t *symbol_ids = NULL;
    enum ep_status status = EP_OK;
    int result;

    if (store == NULL || atoms == NULL || atom_count == 0U ||
        term_id == NULL) {
        return EP_INVALID_INPUT;
    }
    symbol_ids = calloc(atom_count, sizeof(*symbol_ids));
    if (symbol_ids == NULL) {
        return EP_INTERNAL;
    }
    if (sqlite3_exec(store->database, "BEGIN IMMEDIATE;", NULL, NULL, NULL) !=
        SQLITE_OK) {
        free(symbol_ids);
        return EP_STORAGE;
    }
    for (size_t index = 0U; index < atom_count; ++index) {
        status = ep_resolve_symbol(store->database, &atoms[index],
                                   &symbol_ids[index]);
        if (status != EP_OK) {
            goto rollback;
        }
    }

    status = ep_find_exact_term(store->database, symbol_ids, atom_count,
                                term_id);
    if (status == EP_OK) {
        sqlite3_exec(store->database, "COMMIT;", NULL, NULL, NULL);
        free(symbol_ids);
        return EP_OK;
    }
    if (status != EP_NOT_FOUND) {
        goto rollback;
    }

    result = sqlite3_prepare_v2(
        store->database,
        "INSERT INTO core_term DEFAULT VALUES;",
        -1, &statement, NULL);
    if (result == SQLITE_OK) {
        result = sqlite3_step(statement);
    }
    sqlite3_finalize(statement);
    if (result != SQLITE_DONE) {
        status = ep_sqlite_status(result);
        goto rollback;
    }
    *term_id = sqlite3_last_insert_rowid(store->database);
    result = sqlite3_prepare_v2(
        store->database,
        "INSERT INTO core_termsymbol(\"order\", symbol_id, term_id) "
        "VALUES (?1, ?2, ?3);",
        -1, &statement, NULL);
    if (result == SQLITE_OK) {
        for (size_t index = 0U; index < atom_count; ++index) {
            sqlite3_bind_int(statement, 1, (int)index);
            sqlite3_bind_int64(statement, 2, (sqlite3_int64)symbol_ids[index]);
            sqlite3_bind_int64(statement, 3, (sqlite3_int64)*term_id);
            result = sqlite3_step(statement);
            if (result != SQLITE_DONE) {
                break;
            }
            sqlite3_reset(statement);
            sqlite3_clear_bindings(statement);
        }
    }
    sqlite3_finalize(statement);
    if (result != SQLITE_DONE) {
        status = ep_sqlite_status(result);
        goto rollback;
    }
    if (sqlite3_exec(store->database, "COMMIT;", NULL, NULL, NULL) !=
        SQLITE_OK) {
        status = EP_STORAGE;
        goto rollback;
    }
    free(symbol_ids);
    return EP_OK;

rollback:
    sqlite3_exec(store->database, "ROLLBACK;", NULL, NULL, NULL);
    free(symbol_ids);
    return status;
}

static enum ep_status ep_read_term(sqlite3 *database, int64_t term_id,
                                   struct ep_owned_blob *atoms,
                                   size_t atom_count) {
    sqlite3_stmt *statement = NULL;
    int result;
    size_t count = 0U;

    result = sqlite3_prepare_v2(
        database,
        "SELECT ts.\"order\", s.symbol FROM core_termsymbol AS ts "
        "JOIN core_symbol AS s ON s.id=ts.symbol_id "
        "WHERE ts.term_id=?1 ORDER BY ts.\"order\";",
        -1, &statement, NULL);
    if (result != SQLITE_OK) {
        return ep_sqlite_status(result);
    }
    sqlite3_bind_int64(statement, 1, term_id);
    while ((result = sqlite3_step(statement)) == SQLITE_ROW) {
        const void *data = sqlite3_column_blob(statement, 1);
        int length = sqlite3_column_bytes(statement, 1);
        int order = sqlite3_column_int(statement, 0);
        if (order < 0 || (size_t)order >= atom_count || length < 0 ||
            (length > 0 && data == NULL)) {
            sqlite3_finalize(statement);
            return EP_CORRUPT;
        }
        atoms[order].data = malloc((size_t)length);
        if (length > 0 && atoms[order].data == NULL) {
            sqlite3_finalize(statement);
            return EP_INTERNAL;
        }
        if (length > 0) {
            memcpy(atoms[order].data, data, (size_t)length);
        }
        atoms[order].length = (size_t)length;
        ++count;
    }
    sqlite3_finalize(statement);
    if (result != SQLITE_DONE) {
        return ep_sqlite_status(result);
    }
    return count == atom_count ? EP_OK : EP_NOT_FOUND;
}

enum ep_status ep_store_query_environment(
    struct ep_store *store,
    const struct ep_blob *start_timestamp,
    const struct ep_blob *end_timestamp,
    size_t limit,
    ep_term_callback callback,
    void *context) {
    sqlite3_stmt *statement = NULL;
    int result;
    size_t count = 0U;
    enum ep_status status = EP_OK;

    if (store == NULL || callback == NULL || limit == 0U) {
        return EP_INVALID_INPUT;
    }
    result = sqlite3_prepare_v2(
        store->database,
        "SELECT ts.term_id FROM core_termsymbol AS ts "
        "JOIN core_symbol AS s ON s.id=ts.symbol_id "
        "WHERE ts.\"order\"=1 "
        "AND (?1 IS NULL OR s.symbol >= ?1) "
        "AND (?2 IS NULL OR s.symbol <= ?2) "
        "ORDER BY s.symbol ASC, ts.term_id ASC LIMIT ?3;",
        -1, &statement, NULL);
    if (result != SQLITE_OK) {
        return ep_sqlite_status(result);
    }
    if (start_timestamp != NULL) {
        ep_bind_blob(statement, 1, start_timestamp);
    } else {
        sqlite3_bind_null(statement, 1);
    }
    if (end_timestamp != NULL) {
        ep_bind_blob(statement, 2, end_timestamp);
    } else {
        sqlite3_bind_null(statement, 2);
    }
    sqlite3_bind_int64(statement, 3, (sqlite3_int64)limit);
    while ((result = sqlite3_step(statement)) == SQLITE_ROW) {
        struct ep_owned_blob atoms[EP_ENVIRONMENT_ATOM_COUNT] = {0};
        int callback_result;
        status = ep_read_term(store->database, sqlite3_column_int64(statement, 0),
                              atoms, EP_ENVIRONMENT_ATOM_COUNT);
        if (status == EP_OK) {
            callback_result = callback(sqlite3_column_int64(statement, 0),
                                       atoms, EP_ENVIRONMENT_ATOM_COUNT, context);
            ep_owned_blobs_reset(atoms, EP_ENVIRONMENT_ATOM_COUNT);
            if (callback_result != 0) {
                status = EP_OK;
                break;
            }
            ++count;
        } else {
            ep_owned_blobs_reset(atoms, EP_ENVIRONMENT_ATOM_COUNT);
        }
    }
    if (result != SQLITE_DONE && result != SQLITE_ROW) {
        status = ep_sqlite_status(result);
    }
    sqlite3_finalize(statement);
    (void)count;
    return status;
}

void ep_owned_blobs_reset(struct ep_owned_blob *atoms, size_t atom_count) {
    if (atoms == NULL) {
        return;
    }
    for (size_t index = 0U; index < atom_count; ++index) {
        free(atoms[index].data);
        atoms[index].data = NULL;
        atoms[index].length = 0U;
    }
}

const char *ep_status_name(enum ep_status status) {
    switch (status) {
    case EP_OK: return "ok";
    case EP_INVALID_INPUT: return "invalid-input";
    case EP_NOT_FOUND: return "not-found";
    case EP_CONFLICT: return "conflict";
    case EP_STORAGE: return "storage";
    case EP_CORRUPT: return "corrupt";
    case EP_INTERNAL: return "internal";
    default: return "unknown";
    }
}
