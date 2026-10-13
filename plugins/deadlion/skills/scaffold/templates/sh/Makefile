.POSIX:
# __NAME__ - copy files to standard output
# See LICENSE file for copyright and license details.

# the version lives at the top of __NAME__ only
VERSION = `sed -n 's/^VERSION=//p' __NAME__ | sed 1q`
PREFIX = /usr/local
MANPREFIX = $(PREFIX)/share/man

all:
	@:

test:
	BIN=./__NAME__ sh test.sh

clean:
	rm -f __NAME__-$(VERSION).tar.gz

dist:
	mkdir -p __NAME__-$(VERSION)
	cp -R LICENSE Makefile README __NAME__ __NAME__.1 test.sh __NAME__-$(VERSION)
	tar -cf - __NAME__-$(VERSION) | gzip > __NAME__-$(VERSION).tar.gz
	rm -rf __NAME__-$(VERSION)

install:
	mkdir -p $(DESTDIR)$(PREFIX)/bin
	cp -f __NAME__ $(DESTDIR)$(PREFIX)/bin
	chmod 755 $(DESTDIR)$(PREFIX)/bin/__NAME__
	mkdir -p $(DESTDIR)$(MANPREFIX)/man1
	sed "s/VERSION/$(VERSION)/g" < __NAME__.1 > $(DESTDIR)$(MANPREFIX)/man1/__NAME__.1
	chmod 644 $(DESTDIR)$(MANPREFIX)/man1/__NAME__.1

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/__NAME__ \
		$(DESTDIR)$(MANPREFIX)/man1/__NAME__.1

.PHONY: all test clean dist install uninstall
