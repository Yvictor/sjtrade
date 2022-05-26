
install: install-flit
	flit install -s

install-flit:
	pip install flit

test-cov:
	pytest --cov=sjtrade tests --cov-report xml:cov.xml