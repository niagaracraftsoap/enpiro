#include "enpiro_store.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

struct query_state {
    size_t count;
    int64_t last_term;
};

static int count_term(int64_t term_id, const struct ep_owned_blob *atoms,
                      size_t atom_count, void *context) {
    struct query_state *state = context;
    assert(atom_count == 5U);
    assert(atoms[0].length == 5U);
    assert(memcmp(atoms[0].data, "local", 5U) == 0);
    assert(atoms[1].length == 8U);
    ++state->count;
    state->last_term = term_id;
    return 0;
}

int main(void) {
    const char *path = "/tmp/enpiro-native-store-test.sqlite";
    const unsigned char source[] = "local";
    const unsigned char timestamp_one[8] = {0, 0, 0, 0, 0, 0, 0, 1};
    const unsigned char timestamp_two[8] = {0, 0, 0, 0, 0, 0, 0, 2};
    const unsigned char temperature[] = {0, 224};
    const unsigned char pressure[] = {3, 245};
    const unsigned char humidity[] = {2, 0};
    struct ep_blob first[] = {
        {source, sizeof(source) - 1U}, {timestamp_one, sizeof(timestamp_one)},
        {temperature, sizeof(temperature)}, {pressure, sizeof(pressure)},
        {humidity, sizeof(humidity)},
    };
    struct ep_blob second[] = {
        {source, sizeof(source) - 1U}, {timestamp_two, sizeof(timestamp_two)},
        {temperature, sizeof(temperature)}, {pressure, sizeof(pressure)},
        {humidity, sizeof(humidity)},
    };
    struct ep_store *store = NULL;
    struct query_state state = {0};
    int64_t first_id = 0;
    int64_t duplicate_id = 0;
    int64_t second_id = 0;

    (void)remove(path);
    assert(ep_store_open(path, &store) == EP_OK);
    assert(ep_store_resolve_term(store, first, 5U, &first_id) == EP_OK);
    assert(ep_store_resolve_term(store, first, 5U, &duplicate_id) == EP_OK);
    assert(first_id == duplicate_id);
    assert(ep_store_resolve_term(store, second, 5U, &second_id) == EP_OK);
    assert(second_id != first_id);
    assert(ep_store_query_environment(store, NULL, NULL, 48U, count_term,
                                      &state) == EP_OK);
    assert(state.count == 2U);
    assert(state.last_term == second_id);
    ep_store_close(store);
    (void)remove(path);
    puts("native store tests passed");
    return 0;
}
