.PHONY: lint test package

lint:
	python -m compileall spektor

test:
	python -m unittest discover -s tests -v

package:
	python -m build
