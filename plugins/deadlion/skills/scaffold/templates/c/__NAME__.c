/* See LICENSE file for copyright and license details.
 *
 * __NAME__ - copy files to standard output
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "util.h"

/* function declarations */
static void cat(FILE *fp, const char *name, char *buf);
static void usage(void);

/* configuration, allows nested code to access above variables */
#include "config.h"

/* function implementations */
static void
cat(FILE *fp, const char *name, char *buf)
{
	size_t n;

	while ((n = fread(buf, 1, bufsize, fp)) > 0)
		if (fwrite(buf, 1, n, stdout) != n)
			die("__NAME__: write error:");
	if (ferror(fp))
		die("__NAME__: %s:", name);
}

static void
usage(void)
{
	die("usage: __NAME__ [-v] [file...]");
}

int
main(int argc, char *argv[])
{
	FILE *fp;
	char *buf;
	int c, i;

	while ((c = getopt(argc, argv, "v")) != -1) {
		switch (c) {
		case 'v':
			puts("__NAME__-" VERSION);
			return 0;
		default:
			usage();
		}
	}

	buf = ecalloc(bufsize, 1);
	if (optind == argc)
		cat(stdin, "<stdin>", buf);
	for (i = optind; i < argc; i++) {
		if (!strcmp(argv[i], "-")) {
			cat(stdin, "<stdin>", buf);
			continue;
		}
		if (!(fp = fopen(argv[i], "r")))
			die("__NAME__: %s:", argv[i]);
		cat(fp, argv[i], buf);
		fclose(fp);
	}
	free(buf);

	if (fflush(stdout) == EOF || ferror(stdout))
		die("__NAME__: write error:");
	return 0;
}
