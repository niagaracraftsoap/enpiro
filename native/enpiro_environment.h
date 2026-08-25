#ifndef ENPIRO_ENVIRONMENT_H
#define ENPIRO_ENVIRONMENT_H

#include "enpiro_store.h"

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EP_ENVIRONMENT_SOURCE_MAX 255U

struct ep_environment {
    int64_t observed_at_us;
    double temperature_c;
    double pressure_hpa;
    double relative_humidity;
    char source_id[EP_ENVIRONMENT_SOURCE_MAX + 1U];
};

typedef int (*ep_environment_callback)(const struct ep_environment *value,
                                        int64_t term_id,
                                        void *context);

enum ep_status ep_environment_save(struct ep_store *store,
                                   const struct ep_environment *value,
                                   int64_t *term_id);

enum ep_status ep_environment_decode(const struct ep_owned_blob *atoms,
                                     size_t atom_count,
                                     struct ep_environment *out);

enum ep_status ep_environment_query(
    struct ep_store *store,
    const struct ep_environment *start,
    const struct ep_environment *end,
    size_t limit,
    ep_environment_callback callback,
    void *context);

#ifdef __cplusplus
}
#endif

#endif
