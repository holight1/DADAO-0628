typedef unsigned long size_t;

void *malloc(size_t);
void free(void *);

enum {
	EXIT_NULL = 10,
	EXIT_FIRST_BYTE = 11,
	EXIT_LAST_BYTE = 12,
	EXIT_BEFORE_FREE_MARKER = 13,
	EXIT_AFTER_FREE_PRESERVE = 14,
	EXIT_AFTER_FREE_MARKER = 15,
	EXIT_OK = 42
};

static volatile unsigned long phase_marker;

int main(void)
{
	volatile unsigned char *first;
	volatile unsigned char *last;
	unsigned char *p = (unsigned char *)malloc(131052UL);

	if (!p)
		return EXIT_NULL;

	first = (volatile unsigned char *)p;
	*first = 0xa5;
	if (*first != 0xa5)
		return EXIT_FIRST_BYTE;

	last = (volatile unsigned char *)(p + 131051UL);
	*last = 0x5a;
	if (*last != 0x5a)
		return EXIT_LAST_BYTE;

	phase_marker = 0x13579bdfUL;
	if (phase_marker != 0x13579bdfUL)
		return EXIT_BEFORE_FREE_MARKER;

	free(p);

	if (phase_marker != 0x13579bdfUL)
		return EXIT_AFTER_FREE_PRESERVE;
	phase_marker = 0x2468ace0UL;
	if (phase_marker != 0x2468ace0UL)
		return EXIT_AFTER_FREE_MARKER;

	return EXIT_OK;
}
