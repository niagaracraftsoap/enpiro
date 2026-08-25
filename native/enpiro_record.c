#include "enpiro_environment.h"

#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int parse_i64(const char *text, int64_t *value) {
    char *end = NULL;
    long long parsed;
    if (text == NULL || value == NULL || *text == '\0') return 0;
    errno = 0;
    parsed = strtoll(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') return 0;
    *value = (int64_t)parsed;
    return 1;
}

static int parse_double(const char *text, double *value) {
    char *end = NULL;
    double parsed;
    if (text == NULL || value == NULL || *text == '\0') return 0;
    errno = 0;
    parsed = strtod(text, &end);
    if (errno != 0 || end == text || *end != '\0' || !isfinite(parsed)) return 0;
    *value = parsed;
    return 1;
}

int main(int argc, char **argv) {
    struct ep_store *store = NULL;
    struct ep_environment value;
    int64_t term_id;
    enum ep_status status;

    if (argc != 7) {
        fprintf(stderr, "Usage: %s DATABASE OBSERVED_AT_US TEMPERATURE_C PRESSURE_HPA HUMIDITY_PERCENT SOURCE_ID\n", argv[0]);
        return EXIT_FAILURE;
    }
    memset(&value, 0, sizeof(value));
    if (!parse_i64(argv[2], &value.observed_at_us) ||
        !parse_double(argv[3], &value.temperature_c) ||
        !parse_double(argv[4], &value.pressure_hpa) ||
        !parse_double(argv[5], &value.relative_humidity) ||
        argv[6][0] == '\0' || strlen(argv[6]) > EP_ENVIRONMENT_SOURCE_MAX) {
        fprintf(stderr, "invalid observation value\n");
        return EXIT_FAILURE;
    }
    memcpy(value.source_id, argv[6], strlen(argv[6]) + 1U);

    status = ep_store_open(argv[1], &store);
    if (status == EP_OK) status = ep_environment_save(store, &value, &term_id);
    ep_store_close(store);
    if (status != EP_OK) {
        fprintf(stderr, "cannot record observation: %s\n", ep_status_name(status));
        return EXIT_FAILURE;
    }
    printf("%" PRId64 "\n", term_id);
    return EXIT_SUCCESS;
}
