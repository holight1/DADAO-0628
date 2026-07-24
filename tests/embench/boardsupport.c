/*
 * DADAO board glue for the Embench functional-correctness sweep.
 *
 * Timing and score collection are deliberately outside ML-032a.  These
 * hooks therefore have no observable effect; support/main.c still executes
 * benchmark() once and returns !verify_benchmark(result).
 */

void
initialise_board (void)
{
}

void
start_trigger (void)
{
}

void
stop_trigger (void)
{
}
