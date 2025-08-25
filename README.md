# Competency Management App for Genetics

A Django-based web application designed for the genetics team to manage employee competencies. The platform allows for uploading evidence, signing off on skills, assigning tasks, and maintaining a comprehensive record of team capabilities.

## Key Features

* **Competency Tracking:** Record and manage a list of all required competencies.
* **Evidence Uploads:** Users can upload files as evidence of their skills.
* **Sign-off Workflow:** A system for managers or senior staff to review and sign off on completed competencies.
* **Assignment & Reporting:** Assign competencies to team members and view progress reports.
* **User Management:** Built-in Django admin panel for managing users and permissions.

## Project Structure

The project follows a standard Django layout:

```text
CompetencyApp/
├── competency/           # The main Django app for all competency logic
│   ├── migrations/       # Database migration files
│   ├── static/           # Static files (CSS, JavaScript, Images)
│   ├── templates/        # HTML templates
│   ├── models.py         # Database models (the schema)
│   ├── views.py          # Application logic (request handling)
│   ├── urls.py           # URL routing
│   └── admin.py          # Configuration for the Django admin site
│
├── CompetencyApp/        # The main Django project configuration
│   ├── settings.py       # Project settings
│   └── urls.py           # Top-level URL routing
│
├── venv/                 # Virtual environment files
├── db.sqlite3            # Development database file
└── manage.py             # Django's command-lines