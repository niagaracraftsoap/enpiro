#include "enpiro_environment.h"

#include <math.h>
#include <string.h>

#define EP_ENVIRONMENT_ATOM_COUNT 5U

static void ep_write_u16(unsigned char output[2], uint16_t value) {
    output[0] = (unsigned char)(value >> 8U);
    output[1] = (unsigned char)value;
}

static void ep_write_i64(unsigned char output[8], int64_t value) {
    uint64_t unsigned_value = (uint64_t)value;
    for (size_t index = 0U; index < 8U; ++index) {
        output[7U - index] = (unsigned char)(unsigned_value >> (index * 8U));
    }
}

static uint16_t ep_read_u16(const unsigned char input[2]) {
    return (uint16_t)(((uint16_t)input[0] << 8U) | input[1]);
}

static int64_t ep_read_i64(const unsigned char input[8]) {
    uint64_t value = 0U;
    for (size_t index = 0U; index < 8U; ++index) {
        value = (value << 8U) | input[index];
    }
    return (int64_t)value;
}

static enum ep_status ep_encode(const struct ep_environment *value,
                                struct ep_blob atoms[EP_ENVIRONMENT_ATOM_COUNT],
                                unsigned char source[EP_ENVIRONMENT_SOURCE_MAX + 1U],
                                unsigned char timestamp[8],
                                unsigned char temperature[2],
                                unsigned char pressure[2],
                                unsigned char humidity[2]) {
    double temperature_units;
    double pressure_units;
    double humidity_units;

    if (value == NULL || value->source_id[0] == '\0' ||
        strlen(value->source_id) > EP_ENVIRONMENT_SOURCE_MAX ||
        !isfinite(value->temperature_c) || !isfinite(value->pressure_hpa) ||
        !isfinite(value->relative_humidity)) {
        return EP_INVALID_INPUT;
    }
    temperature_units = round(value->temperature_c * 10.0);
    pressure_units = round(value->pressure_hpa);
    humidity_units = round(value->relative_humidity * 10.0);
    if (temperature_units < -32768.0 || temperature_units > 32767.0 ||
        pressure_units < 0.0 || pressure_units > 65535.0 ||
        humidity_units < 0.0 || humidity_units > 1000.0) {
        return EP_INVALID_INPUT;
    }
    memcpy(source, value->source_id, strlen(value->source_id));
    source[strlen(value->source_id)] = '\0';
    ep_write_i64(timestamp, value->observed_at_us);
    ep_write_u16(temperature, (uint16_t)(int16_t)temperature_units);
    ep_write_u16(pressure, (uint16_t)pressure_units);
    ep_write_u16(humidity, (uint16_t)humidity_units);
    atoms[0] = (struct ep_blob){source, strlen(value->source_id)};
    atoms[1] = (struct ep_blob){timestamp, 8U};
    atoms[2] = (struct ep_blob){temperature, 2U};
    atoms[3] = (struct ep_blob){pressure, 2U};
    atoms[4] = (struct ep_blob){humidity, 2U};
    return EP_OK;
}

enum ep_status ep_environment_save(struct ep_store *store,
                                   const struct ep_environment *value,
                                   int64_t *term_id) {
    struct ep_blob atoms[EP_ENVIRONMENT_ATOM_COUNT];
    unsigned char source[EP_ENVIRONMENT_SOURCE_MAX + 1U];
    unsigned char timestamp[8];
    unsigned char temperature[2];
    unsigned char pressure[2];
    unsigned char humidity[2];
    enum ep_status status = ep_encode(value, atoms, source, timestamp,
                                       temperature, pressure, humidity);
    if (status != EP_OK) {
        return status;
    }
    return ep_store_resolve_term(store, atoms, EP_ENVIRONMENT_ATOM_COUNT,
                                 term_id);
}

enum ep_status ep_environment_decode(const struct ep_owned_blob *atoms,
                                     size_t atom_count,
                                     struct ep_environment *out) {
    size_t source_length;
    int16_t temperature_units;

    if (atoms == NULL || out == NULL || atom_count != EP_ENVIRONMENT_ATOM_COUNT ||
        atoms[0].length == 0U || atoms[0].length > EP_ENVIRONMENT_SOURCE_MAX ||
        atoms[1].length != 8U || atoms[2].length != 2U ||
        atoms[3].length != 2U || atoms[4].length != 2U) {
        return EP_INVALID_INPUT;
    }
    source_length = atoms[0].length;
    memcpy(out->source_id, atoms[0].data, source_length);
    out->source_id[source_length] = '\0';
    temperature_units = (int16_t)ep_read_u16(atoms[2].data);
    out->observed_at_us = ep_read_i64(atoms[1].data);
    out->temperature_c = (double)temperature_units / 10.0;
    out->pressure_hpa = (double)ep_read_u16(atoms[3].data);
    out->relative_humidity = (double)ep_read_u16(atoms[4].data) / 10.0;
    return EP_OK;
}

struct ep_environment_query_context {
    ep_environment_callback callback;
    void *context;
};

static int ep_environment_query_term(int64_t term_id,
                                     const struct ep_owned_blob *atoms,
                                     size_t atom_count, void *context) {
    struct ep_environment_query_context *query_context = context;
    struct ep_environment value;
    if (ep_environment_decode(atoms, atom_count, &value) != EP_OK) {
        return 0;
    }
    return query_context->callback(&value, term_id, query_context->context);
}

enum ep_status ep_environment_query(
    struct ep_store *store,
    const struct ep_environment *start,
    const struct ep_environment *end,
    size_t limit,
    ep_environment_callback callback,
    void *context) {
    struct ep_environment_query_context query_context = {callback, context};
    struct ep_blob start_blob;
    struct ep_blob end_blob;
    unsigned char start_bytes[8];
    unsigned char end_bytes[8];

    if (callback == NULL || limit == 0U) {
        return EP_INVALID_INPUT;
    }
    if (start != NULL) {
        ep_write_i64(start_bytes, start->observed_at_us);
        start_blob = (struct ep_blob){start_bytes, sizeof(start_bytes)};
    }
    if (end != NULL) {
        ep_write_i64(end_bytes, end->observed_at_us);
        end_blob = (struct ep_blob){end_bytes, sizeof(end_bytes)};
    }
    return ep_store_query_environment(
        store, start == NULL ? NULL : &start_blob,
        end == NULL ? NULL : &end_blob, limit,
        ep_environment_query_term, &query_context);
}
