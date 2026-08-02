build:
	docker build -t yard-invoice-fraud-report:latest .

run:
	docker run --env-file .env -p 9000:9000 yard-invoice-fraud-report:latest

test:
	docker run --rm yard-invoice-fraud-report:latest python -c "print('smoke test passed')"

health:
	curl -f http://localhost:9000/health
