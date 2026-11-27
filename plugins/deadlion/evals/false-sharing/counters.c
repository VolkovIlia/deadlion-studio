#define _GNU_SOURCE
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef STRIDE
#define STRIDE 1
#endif

/* Compare independent relaxed counters on a host with 64-byte cache lines. */
_Alignas(64) static _Atomic uint64_t counters[2 * STRIDE];

struct worker {
    size_t index;
    int cpu;
};

static void *increment(void *arg)
{
    struct worker *worker = arg;
    cpu_set_t affinity;
    CPU_ZERO(&affinity);
    CPU_SET(worker->cpu, &affinity);
    if (pthread_setaffinity_np(pthread_self(), sizeof affinity, &affinity))
        return arg;
    for (unsigned i = 0; i < 1000000; ++i)
        atomic_fetch_add_explicit(&counters[worker->index * STRIDE], 1, memory_order_relaxed);
    return NULL;
}

int main(int argc, char **argv)
{
    if (argc != 3)
        return 2;
    struct worker workers[2];
    pthread_t threads[2];
    for (size_t i = 0; i < 2; ++i) {
        char *end;
        long cpu = strtol(argv[i + 1], &end, 10);
        if (end == argv[i + 1] || *end || cpu < 0 || cpu >= CPU_SETSIZE)
            return 2;
        workers[i] = (struct worker){i, (int)cpu};
        if (pthread_create(&threads[i], NULL, increment, &workers[i]))
            return 2;
    }
    for (size_t i = 0; i < 2; ++i) {
        void *error;
        if (pthread_join(threads[i], &error) || error)
            return 2;
    }
    printf("%llu\n", (unsigned long long)(counters[0] + counters[STRIDE]));
    return 0;
}
