#include "enpiro_environment.h"

#include <assert.h>
#include <stdio.h>

struct query_state {
    size_t count;
    int64_t previous_timestamp;
};

static int observe(const struct ep_environment *value, int64_t term_id,
                   void *context) {
    struct query_state *state = context;
    (void)term_id;
    assert(value->source_id[0] == 'l');
    assert(value->temperature_c == 21.4);
    assert(value->observed_at_us > state->previous_timestamp);
    ++state->count;
    state->previous_timestamp = value->observed_at_us;
    return 0;
}

int main(void) {
    const char *path = "/tmp/enpiro-native-environment-test.sqlite";
    struct ep_store *store = NULL;
    struct ep_environment first = {
        1000000, 21.4, 1012.0, 48.0, "local"
    };
    struct ep_environment second = {
        2000000, 21.4, 1012.0, 48.0, "local"
    };
    struct query_state state = {0};
    int64_t first_id = 0;
    int64_t second_id = 0;

    (void)remove(path);
    assert(ep_store_open(path, &store) == EP_OK);
    assert(ep_environment_save(store, &first, &first_id) == EP_OK);
    assert(ep_environment_save(store, &second, &second_id) == EP_OK);
    assert(first_id != second_id);
    assert(ep_environment_query(store, NULL, NULL, 48U, observe, &state) == EP_OK);
    assert(state.count == 2U);
    assert(state.previous_timestamp == second.observed_at_us);
    ep_store_close(store);
    (void)remove(path);
    puts("native environment tests passed");
    return 0;
}
