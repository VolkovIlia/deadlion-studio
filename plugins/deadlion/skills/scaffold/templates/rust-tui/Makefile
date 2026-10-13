.POSIX:
# __NAME__ - pick a line interactively
# See LICENSE file for copyright and license details.

# the version lives in Cargo.toml only
VERSION = `sed -n 's/^version = "\(.*\)"$$/\1/p' Cargo.toml | sed 1q`
PREFIX = /usr/local
MANPREFIX = $(PREFIX)/share/man
CARGO = cargo

all: src/config.rs
	$(CARGO) build --release --quiet

src/config.rs:
	cp src/config.def.rs src/config.rs

test: all
	$(CARGO) test --quiet
	BIN=target/release/__NAME__ sh test.sh

clean:
	$(CARGO) clean --quiet
	rm -f __NAME__-$(VERSION).tar.gz

Cargo.lock:
	$(CARGO) generate-lockfile --quiet

dist: Cargo.lock
	mkdir -p __NAME__-$(VERSION)
	cp -R LICENSE Makefile README Cargo.toml Cargo.lock __NAME__.1 test.sh src \
		__NAME__-$(VERSION)
	rm -f __NAME__-$(VERSION)/src/config.rs
	tar -cf - __NAME__-$(VERSION) | gzip > __NAME__-$(VERSION).tar.gz
	rm -rf __NAME__-$(VERSION)

install: all
	mkdir -p $(DESTDIR)$(PREFIX)/bin
	cp -f target/release/__NAME__ $(DESTDIR)$(PREFIX)/bin
	chmod 755 $(DESTDIR)$(PREFIX)/bin/__NAME__
	mkdir -p $(DESTDIR)$(MANPREFIX)/man1
	sed "s/VERSION/$(VERSION)/g" < __NAME__.1 > $(DESTDIR)$(MANPREFIX)/man1/__NAME__.1
	chmod 644 $(DESTDIR)$(MANPREFIX)/man1/__NAME__.1

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/__NAME__ \
		$(DESTDIR)$(MANPREFIX)/man1/__NAME__.1

.PHONY: all test clean dist install uninstall
