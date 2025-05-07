import os
from django.utils import timezone
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.db import connections
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required


def get_employee_id_from_user(user):
    """Retrieve the employee ID from Emps_GO based on the user's email."""
    email = user.email
    with connections['default'].cursor() as cursor:
        cursor.execute("SELECT id FROM dbo.Emps_GO WHERE EmailAddress = %s", [email])
        row = cursor.fetchone()
        return row[0] if row else None


def user_login(request):
    """Login view using Django's built-in auth system."""
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

            # Get employee ID and store in session
            employee_id = get_employee_id_from_user(user)
            if employee_id:
                request.session["employee_id"] = employee_id

                # 🔍 Get employee's full name
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT FirstName, LastName FROM dbo.Emps_GO WHERE id = %s", [employee_id])
                    row = cursor.fetchone()
                full_name = f"{row[0]} {row[1]}" if row else None

                # 🔗 Check if that full name exists in LineManagers table (cross DB)
                is_manager = False
                if full_name:
                    with connections["competency_db"].cursor() as cursor:
                        cursor.execute("SELECT Id FROM dbo.LineManagers WHERE Name = %s", [full_name])
                        lm_row = cursor.fetchone()

                    if lm_row:
                        lm_id = lm_row[0]
                        with connections["default"].cursor() as cursor:
                            cursor.execute("SELECT COUNT(*) FROM dbo.Emps_GO WHERE LineManagerId = %s", [lm_id])
                            count = cursor.fetchone()[0]
                            is_manager = count > 0

                request.session["is_line_manager"] = is_manager

            return redirect("home")
        else:
            return render(request, "competency/login.html", {"error": "Invalid credentials"})

    return render(request, "competency/login.html")


@login_required
def home(request):
    """Home dashboard showing progress and greeting."""
    full_name = None
    approved_percent = 0
    employee_id = request.session.get("employee_id")
    is_line_manager = request.session.get("is_line_manager", False)

    if not employee_id:
        employee_id = get_employee_id_from_user(request.user)
        request.session["employee_id"] = employee_id

    if employee_id:
        with connections["default"].cursor() as cursor:
            cursor.execute("""
                SELECT FirstName, LastName
                FROM dbo.Emps_GO
                WHERE id = %s
            """, [employee_id])
            row = cursor.fetchone()
            if row:
                full_name = f"{row[0]} {row[1]}"

            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END),
                    COUNT(*)
                FROM dbo.competency_user
                WHERE employee_id = %s
            """, [employee_id])
            approved, total = cursor.fetchone()
            approved_percent = round((approved or 0) / total * 100, 2) if total else 0

    return render(request, "competency/home.html", {
        "full_name": full_name,
        "approved_percent": approved_percent,
        "is_line_manager": is_line_manager
    })


@login_required
def competency(request):
    """Show user's personal competencies and stats."""
    email = request.user.email
    employee_id = request.session.get("employee_id")

    if not employee_id:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT id FROM dbo.Emps_GO WHERE EmailAddress = %s", [email])
            row = cursor.fetchone()
            if not row:
                return HttpResponse("Employee not found.")
            employee_id = row[0]
            request.session["employee_id"] = employee_id

    with connections["default"].cursor() as cursor:
        cursor.execute("""
            SELECT competency_name, progress, status
            FROM dbo.competency_user
            WHERE employee_id = %s
        """, [employee_id])
        results = cursor.fetchall()

    competencies = []
    approved = pending = 0

    for name, progress, status in results:
        competencies.append({'name': name, 'progress': progress, 'status': status})
        if status.lower() == 'approved':
            approved += 1
        elif status.lower() == 'pending':
            pending += 1

    total = approved + pending
    approved_percent = round((approved / total) * 100, 2) if total else 0
    pending_percent = round((pending / total) * 100, 2) if total else 0

    return render(request, "competency/competency.html", {
        "employee_id": employee_id,
        "approved_percent": approved_percent,
        "pending_percent": pending_percent,
        "competencies": competencies,
        "is_line_manager": request.session.get("is_line_manager", False)
    })


def portfolio(request):
    return render(request, "competency/portfolio.html")


def tasks(request):
    return render(request, "competency/tasks.html")


def submissions(request):
    return render(request, "competency/submissions.html")


def messages(request):
    return render(request, "competency/messages.html")


@login_required
def create_submission(request):
    user = request.user
    employee_id = get_employee_id_from_user(user)
    message = None
    error = None

    if not employee_id:
        return HttpResponse("Employee record not found.")

    # Fetch competencies
    with connections['default'].cursor() as cursor:
        cursor.execute("""
            SELECT competency_name 
            FROM dbo.competency_user 
            WHERE employee_id = %s
        """, [employee_id])
        competencies = [row[0] for row in cursor.fetchall()]

    # Fetch line managers (assessors)
    with connections['competency_db'].cursor() as cursor:
        cursor.execute("SELECT Name FROM dbo.LineManagers")
        assessors = [row[0] for row in cursor.fetchall()]

    if request.method == "POST" and request.FILES.getlist('evidence_file'):
        files = request.FILES.getlist('evidence_file')
        description = request.POST.get('description', '')
        username = user.username
        selected_assessor = request.POST.get("assessor")

        user_folder = os.path.join(settings.MEDIA_ROOT, username)
        os.makedirs(user_folder, exist_ok=True)

        if not os.path.exists(settings.MEDIA_ROOT):
            error = "Upload folder not found. Please create the folder at G:/EvidenceUploads first."
        else:
            for uploaded_file in files:
                save_path = os.path.join(user_folder, uploaded_file.name)

                # Save file
                with open(save_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)

                # Insert into database
                with connections['default'].cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO dbo.evidence (name, username, file_path, description, uploaded_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, [
                        uploaded_file.name,
                        username,
                        save_path,
                        description,
                        timezone.now()
                    ])

            message = "All files uploaded successfully."

    return render(request, "competency/create_submission.html", {
        "competencies": competencies,
        "assessors": assessors,
        "message": message,
        "error": error,
        "is_line_manager": request.session.get("is_line_manager", False)
    })


@login_required
def team_dashboard(request):
    """Line managers can view the competency status of their team."""
    # Step 1: Get full name from Emps_GO
    employee_id = get_employee_id_from_user(request.user)
    if not employee_id:
        return HttpResponse("Employee not found.")

    with connections['default'].cursor() as cursor:
        cursor.execute("""
            SELECT FirstName, LastName FROM dbo.Emps_GO WHERE id = %s
        """, [employee_id])
        row = cursor.fetchone()
        if not row:
            return HttpResponse("Unable to fetch your full name.")
        full_name = f"{row[0]} {row[1]}"

    # Step 2: Match full name to LineManagers.Name
    with connections['competency_db'].cursor() as cursor:
        cursor.execute("""
            SELECT Id FROM dbo.LineManagers WHERE Name = %s
        """, [full_name])
        row = cursor.fetchone()
        if not row:
            return HttpResponse("You're not listed as a line manager.")
        line_manager_id = row[0]

    # Step 3: Get employees who report to this manager
    with connections['default'].cursor() as cursor:
        cursor.execute("""
            SELECT 
                E.Id, E.FirstName, E.LastName,
                CU.competency_name, CU.status
            FROM dbo.Emps_GO E
            LEFT JOIN dbo.competency_user CU ON E.Id = CU.employee_id
            WHERE E.LineManagerId = %s
            ORDER BY E.LastName
        """, [line_manager_id])
        results = cursor.fetchall()

    # Step 4: Format team data
    team_data = {}
    for emp_id, first, last, comp, status in results:
        name = f"{first} {last}"
        if emp_id not in team_data:
            team_data[emp_id] = {
                "name": name,
                "competencies": []
            }
        if comp:
            team_data[emp_id]["competencies"].append({
                "name": comp,
                "status": status
            })

    return render(request, "competency/team_dashboard.html", {
        "team": team_data,
        "is_line_manager": True
    })




















