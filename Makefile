
install: install-flit
	flit install -s

install-flit:
	pip install flit

test-cov:
	pytest --cov=sjtrade tests --cov-report xml:cov.xml

test:
	pytest --disable-pytest-warnings

testvv:
	pytest -vv --disable-pytest-warnings

test-cov-html:
	pytest --cov=sjtrade tests --cov-report html:cov_html --disable-pytest-warnings