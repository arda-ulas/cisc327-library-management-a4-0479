# Library Management System - Flask Web Application with SQLite
[![Python tests](https://github.com/arda-ulas/cisc327-library-management-a3-0479/actions/workflows/pytest.yml/badge.svg)](https://github.com/arda-ulas/cisc327-library-management-a3-0479/actions/workflows/pytest.yml)

## Overview

This project contains a partial implementation of a Flask-based Library Management System with SQLite database, designed for CISC 327 (Software Quality Assurance) coursework.

Students are provided with:

- [`requirements_specification.md`](requirements_specification.md): Complete requirements document with 7 functional requirements (R1-R7)
- [`app.py`](app.py): Main Flask application with application factory pattern
- [`routes/`](routes/): Modular Flask blueprints for different functionalities
  - [`catalog_routes.py`](routes/catalog_routes.py): Book catalog display and management routes
  - [`borrowing_routes.py`](routes/borrowing_routes.py): Book borrowing and return routes
  - [`api_routes.py`](routes/api_routes.py): JSON API endpoints for late fees and search
  - [`search_routes.py`](routes/search_routes.py): Book search functionality routes
- [`database.py`](database.py): Database operations and SQLite functions
- [`services/library_service.py`](services/library_service.py): **Business logic layer** — implements requirements R1–R7 and A3 payment logic
- [`services/payment_service.py`](services/payment_service.py): Mockable external payment gateway module (added in A3)
- [`templates/`](templates/): HTML templates for the web interface
- [`requirements.txt`](requirements.txt): Python dependencies

## Database Schema
**Books Table:**
- `id` (INTEGER PRIMARY KEY)
- `title` (TEXT NOT NULL)
- `author` (TEXT NOT NULL)  
- `isbn` (TEXT UNIQUE NOT NULL)
- `total_copies` (INTEGER NOT NULL)
- `available_copies` (INTEGER NOT NULL)

**Borrow Records Table:**
- `id` (INTEGER PRIMARY KEY)
- `patron_id` (TEXT NOT NULL)
- `book_id` (INTEGER FOREIGN KEY)
- `borrow_date` (TEXT NOT NULL)
- `due_date` (TEXT NOT NULL)
- `return_date` (TEXT NULL)

## Assignment 3 (Mocking, Stubbing, and Coverage)

This A3 build introduces new payment-related functions and corresponding tests:
- `pay_late_fees()` and `refund_late_fee_payment()` implemented in `services/library_service.py`
- External gateway interactions simulated through mocks (`PaymentGateway`)
- Database and fee retrievals simulated through stubs
- Achieved **~87% coverage** in `library_service.py` and **77% total project coverage**

Coverage report is generated using:
```bash
pytest --cov=services --cov-report=html
```

HTML report can be viewed locally at:
```
htmlcov/index.html
```

## Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Pytest Framework](https://realpython.com/pytest-python-testing/)
- [Test-Driven Development in Python](https://www.datacamp.com/tutorial/test-driven-development-in-python)
