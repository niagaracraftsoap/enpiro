#include "enpiro_store.h"

#include <stdio.h>

static int print_term(int64_t term_id, const struct ep_owned_blob *atoms,
                      size_t atom_count, void *context) {
    (void)context;
    printf("term=%lld atoms=%zu timestamp_bytes=%zu\n",
           (long long)term_id, atom_count, atoms[1].length);
    return 0;
}

int main(int argc, char **argv) {
    struct ep_store *store = NULL;
    enum ep_status status;

    if (argc != 2) {
        fprintf(stderr, "usage: %s DATABASE\n", argv[0]);
        return 2;
    }
    status = ep_store_open(argv[1], &store);
    if (status != EP_OK) {
        fprintf(stderr, "open failed: %s\n", ep_status_name(status));
        return 1;
    }
    status = ep_store_query_environment(store, NULL, NULL, 48,
                                         print_term, NULL);
    ep_store_close(store);
    if (status != EP_OK) {
        fprintf(stderr, "query failed: %s\n", ep_status_name(status));
        return 1;
    }
    return 0;
}
