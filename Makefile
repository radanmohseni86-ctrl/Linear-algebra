MAIN = jozve

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex tex/*.tex chapters/*.tex
	latexmk $(MAIN).tex
	cp build/$(MAIN).pdf $(MAIN).pdf

clean:
	latexmk -C $(MAIN).tex
	rm -rf build

web: $(MAIN).pdf
	cd web && npm install --no-audit --no-fund
	python3 web/build.py

.PHONY: all clean web
