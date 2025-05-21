# Invoice Recognition System

A Django-based web application for automated invoice processing and recognition.

## Features

- Invoice image upload and processing
- OCR (Optical Character Recognition) for invoice data extraction
- Automated data validation and verification
- PDF generation for processed invoices
- User-friendly web interface
- Admin dashboard for invoice management

## Technical Requirements

### System Requirements
- Python 3.8 or higher
- Django 3.2.x
- Virtual environment (recommended)

### Dependencies
- Django >= 3.2.0, < 4.0.0
- reportlab >= 3.6.0 (PDF generation)
- Pillow >= 8.0.0 (Image processing)
- python-dateutil >= 2.8.0 (Date handling)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/invoice_recognition.git
cd invoice_recognition
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run migrations:
```bash
python manage.py migrate
```

5. Create a superuser (admin):
```bash
python manage.py createsuperuser
```

6. Run the development server:
```bash
python manage.py runserver
```

## Project Structure

```
invoice_recognition/
├── invoice_ocr/           # Main application directory
│   ├── doc/              # Documentation
│   ├── services/         # Business logic and services
│   ├── templates/        # HTML templates
│   ├── static/          # Static files (CSS, JS, images)
│   ├── migrations/      # Database migrations
│   ├── models.py        # Database models
│   ├── views.py         # View logic
│   ├── urls.py          # URL routing
│   └── admin.py         # Admin interface configuration
├── media/               # User-uploaded files
├── manage.py           # Django management script
└── requirements.txt    # Project dependencies
```

## Usage

1. Access the web interface at `http://localhost:8000`
2. Log in with your credentials
3. Upload invoice images through the web interface
4. View processed invoices and their extracted data
5. Generate PDF reports as needed

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please open an issue in the GitHub repository or contact the development team.
