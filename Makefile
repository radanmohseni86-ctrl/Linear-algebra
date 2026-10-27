MAIN = jozve

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex tex/*.tex chapters/*.tex
	latexmk $(MAIN).tex
	cp build/$(MAIN).pdf $(MAIN).pdf

clean:
	latexmk -C $(MAIN).tex
	rm -rf build

.PHONY: all clean
