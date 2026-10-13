.POSIX:
# __NAME__ - copy files to standard output
# See LICENSE file for copyright and license details.

include config.mk

SRC = __NAME__.c util.c
OBJ = __NAME__.o util.o

all: __NAME__

config.h:
	cp config.def.h config.h

.c.o:
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $<

$(OBJ): config.h config.mk util.h

__NAME__: $(OBJ)
	$(CC) -o $@ $(OBJ) $(LDFLAGS) $(LIBS)

test: __NAME__
	BIN=./__NAME__ sh test.sh

clean:
	rm -f __NAME__ $(OBJ) __NAME__-$(VERSION).tar.gz

dist: clean
	mkdir -p __NAME__-$(VERSION)
	cp -R LICENSE Makefile README config.def.h config.mk __NAME__.1 \
		test.sh util.h $(SRC) __NAME__-$(VERSION)
	tar -cf - __NAME__-$(VERSION) | gzip > __NAME__-$(VERSION).tar.gz
	rm -rf __NAME__-$(VERSION)

install: all
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
