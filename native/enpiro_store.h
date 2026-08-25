#ifndef ENPIRO_STORE_H
#define ENPIRO_STORE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct ep_store;

struct ep_blob {
    const unsigned char *data;
    size_t length;
};

struct ep_owned_blob {
    unsigned char *data;
    size_t length;
};

enum ep_status {
    EP_OK = 0,
    EP_INVALID_INPUT,
    EP_NOT_FOUND,
    EP_CONFLICT,
    EP_STORAGE,
    EP_CORRUPT,
    EP_INTERNAL,
};

typedef int (*ep_term_callback)(int64_t term_id,
                                const struct ep_owned_blob *atoms,
                                size_t atom_count,
                                void *context);

enum ep_status ep_store_open(const char *path, struct ep_store **out);
void ep_store_close(struct ep_store *store);

enum ep_status ep_store_resolve_term(struct ep_store *store,
                                     const struct ep_blob *atoms,
                                     size_t atom_count,
                                     int64_t *term_id);

enum ep_status ep_store_query_environment(
    struct ep_store *store,
    const struct ep_blob *start_timestamp,
    const struct ep_blob *end_timestamp,
    size_t limit,
    ep_term_callback callback,
    void *context);

void ep_owned_blobs_reset(struct ep_owned_blob *atoms, size_t atom_count);
const char *ep_status_name(enum ep_status status);

#ifdef __cplusplus
}
#endif

#endif
