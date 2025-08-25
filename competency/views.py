import os
from django.utils import timezone
from django.conf import settings
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.db import connections
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
import shutil


""" messages_audit logic. """
def log_audit(username, action, target="", details=""):
    timestamp = timezone.now()
    with connections['default'].cursor() as cursor:
        cursor.execute("""
            INSERT INTO messages_audit (username, action, target, timestamp, details)
            VALUES (%s, %s, %s, %s, %s)
        """, [username, action, target, timestamp, details])

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

                # Get employee's full name
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT FirstName, LastName FROM dbo.Emps_GO WHERE id = %s", [employee_id])
                    row = cursor.fetchone()
                full_name = f"{row[0]} {row[1]}" if row else None

                # Check if that full name exists in LineManagers table (cross DB)
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



from .models import CompetencyUser
from .models import Competencies
@login_required
def competency(request):
    """Show user's competencies and stats."""
    employee_id = request.session.get("employee_id")

    if not employee_id:
        employee_id = get_employee_id_from_user(request.user)
        if not employee_id:
            return HttpResponse("Employee not found.")
        request.session["employee_id"] = employee.id

    #ORM query
    user_competencies = CompetencyUser.objects.filter(employee_id=employee_id).select_related('competency')

    competencies = []
    approved = 0
    pending = 0

    for uc in user_competencies:
        competencies.append({
            'name': uc.competency.name,
            'progress': uc.progress,
            'status': uc.status
        })
        if uc.status.lower() == 'approved':
            approved += 1
        elif uc.status.lower() in ['pending', 'rejected']:
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

@login_required
def tasks(request):
    is_manager = request.session.get("is_line_manager", False)
    username = request.user.username
    full_name = request.user.get_full_name()

    with connections['default'].cursor() as cursor:
        if is_manager:
            cursor.execute("""
                SELECT 
                    R.id AS task_id,
                    COALESCE(E.name, R.evidence_temp_name) AS evidence_name,
                    COALESCE(E.username, R.username) AS submitted_by, 
                    COALESCE(E.description, R.description) AS description,
                    COALESCE(R.assigned_at, R.resubmitted_at, R.created_at) AS assigned_on,
                    'review' AS task_type
                FROM review_tasks R
                LEFT JOIN evidence E ON R.evidence_id = E.id
                WHERE R.assessor_name = %s AND R.status = 'Pending'
                ORDER BY COALESCE(R.assigned_at, R.resubmitted_at, R.created_at) DESC
            """, [full_name])
        else:

            # This query uses LEFT JOIN and COALESCE to correctly find rejected tasks even if there is no evidence record yet.
            cursor.execute("""
                SELECT 
                    R.id AS task_id,
                    COALESCE(E.name, R.evidence_temp_name) AS evidence_name,
                    COALESCE(E.username, R.username) AS submitted_by,
                    COALESCE(E.description, R.description) AS description,
                    R.reviewed_at AS assigned_on,
                    'resubmit' AS task_type,
                    R.feedback
                FROM review_tasks R
                LEFT JOIN evidence E ON R.evidence_id = E.id
                WHERE COALESCE(E.username, R.username) = %s AND R.status = 'Rejected'
                ORDER BY R.reviewed_at DESC
            """, [username])

        columns = [col[0] for col in cursor.description]
        tasks = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return render(request, "competency/tasks.html", {
        "tasks": tasks,
        "is_line_manager": is_manager
    })



@login_required
def review_task(request, task_id):
    assessor = request.user.get_full_name()

    # Get task details from the database
    with connections['default'].cursor() as cursor:
        cursor.execute("""
            SELECT 
                R.id,
                COALESCE(E.name, R.evidence_temp_name) AS file_name,
                COALESCE(E.file_path, R.evidence_temp_path) AS temp_path,
                COALESCE(E.username, R.username) AS submitted_by,
                COALESCE(E.description, R.description) AS description,
                R.status
            FROM review_tasks R
            LEFT JOIN evidence E ON R.evidence_id = E.id
            WHERE R.id = %s AND R.assessor_name = %s
        """, [task_id, assessor])
        row = cursor.fetchone()

        if not row:
            return HttpResponse("Task not found or you are not the assigned assessor.", status=404)

        review_id, file_name, temp_path, submitted_by, description, status = row

    message = None

    if request.method == "POST":
        feedback = request.POST.get("feedback")
        action = request.POST.get("action")
        reviewed_at = timezone.now()
        status_update = "Approved" if action == "approve" else "Rejected"

        with connections['default'].cursor() as cursor:
            if status_update == "Approved":

                temp_full_path = os.path.join(settings.MEDIA_ROOT, temp_path)

                if not os.path.exists(temp_full_path):
                    return HttpResponse(
                        f"Error: The source file could not be found at {temp_full_path}. It may have already been moved or was not uploaded correctly.",
                        status=404)

                final_user_dir = os.path.join(settings.MEDIA_ROOT, submitted_by)
                os.makedirs(final_user_dir, exist_ok=True)
                final_path = os.path.join(final_user_dir, file_name)

                shutil.move(temp_full_path, final_path)

                relative_path = os.path.join(submitted_by, file_name).replace('\\', '/')

                cursor.execute("""
                    INSERT INTO evidence (name, username, file_path, description, uploaded_at)
                    OUTPUT INSERTED.id
                    VALUES (%s, %s, %s, %s, %s)
                """, [file_name, submitted_by, relative_path, description, reviewed_at])
                evidence_id = cursor.fetchone()[0]

                cursor.execute("""
                    UPDATE review_tasks
                    SET status = %s, evidence_id = %s, reviewed_at = %s, feedback = %s,
                        evidence_temp_path = NULL, evidence_temp_name = NULL 
                    WHERE id = %s
                """, [status_update, evidence_id, reviewed_at, feedback, task_id])

                # Correctly calling log_audit for an approved submission
                log_audit(
                    request.user.username,
                    "Approved Submission",
                    file_name,
                    f"Approved evidence for user {submitted_by}"
                )
                message = "Evidence approved and added to portfolio."

            else:  # If action is 'Reject'
                cursor.execute("""
                    UPDATE review_tasks
                    SET status = %s, reviewed_at = %s, feedback = %s
                    WHERE id = %s
                """, [status_update, reviewed_at, feedback, task_id])

                # Correctly calling log_audit for a rejected submission
                log_audit(
                    request.user.username,
                    "Rejected Submission",
                    file_name,
                    f"Rejected evidence for user {submitted_by} with feedback"
                )
                message = "Task has been sent back with feedback."

        status = status_update

    context = {
        "file_name": file_name,
        "file_path": temp_path,
        "submitted_by": submitted_by,
        "description": description,
        "task_id": task_id,
        "status": status,
        "message": message
    }
    return render(request, "competency/review_task.html", context)


@login_required
def download_evidence(request, task_id):
    """
    Securely serves an evidence file for download.
    This view can handle both temporary files and permanent files.
    """
    try:
        user_full_name = request.user.get_full_name()

        with connections['default'].cursor() as cursor:
            # This query gets BOTH the temp path and the permanent path
            cursor.execute("""
                SELECT 
                    R.assessor_name, 
                    R.evidence_temp_path, 
                    E.file_path,
                    E.username
                FROM review_tasks R
                LEFT JOIN evidence E ON R.evidence_id = E.id
                WHERE R.id = %s
            """, [task_id])
            row = cursor.fetchone()

            if not row:
                raise Http404("Task not found.")

            assessor_name, temp_path, permanent_path, evidence_owner_username = row

            # Security Check: Only the assigned assessor or the evidence owner can download
            if user_full_name != assessor_name and request.user.username != evidence_owner_username:
                return HttpResponse("You do not have permission to access this file.", status=403)

            # Determine which path to use. Prioritize the temporary path for pending reviews.
            relative_path = temp_path if temp_path else permanent_path

            if not relative_path:
                return HttpResponse("Error: This task has no associated evidence file path in the database.",
                                    status=404)

            # Construct the absolute path by joining MEDIA_ROOT with the relative path
            file_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            if os.path.exists(file_path):
                # Serve the file for download
                return FileResponse(open(file_path, 'rb'), as_attachment=True)
            else:
                return HttpResponse(
                    f"Error: Could not find the file on the server at the expected location: {file_path}", status=404)

    except Http404 as e:
        return HttpResponse(str(e), status=404)
    except Exception as e:
        return HttpResponse(f"An unexpected error occurred: {e}", status=500)


@login_required
def resubmit_task(request, task_id):
    username = request.user.username
    # First, ensure the task belongs to the user and needs resubmission
    with connections['default'].cursor() as cursor:
        cursor.execute("""
            SELECT R.feedback
            FROM review_tasks R
            LEFT JOIN evidence E ON R.evidence_id = E.id
            WHERE R.id = %s AND COALESCE(E.username, R.username) = %s AND R.status = 'Rejected'
        """, [task_id, username])
        row = cursor.fetchone()

    if not row:
        return HttpResponse("Task not found or is not available for resubmission.", status=404)

    feedback = row[0]

    if request.method == "POST" and request.FILES.get("new_file"):
        new_file = request.FILES["new_file"]
        resubmit_description = request.POST.get("resubmit_description", "")

        # --- THIS IS THE CORRECTED FILE HANDLING LOGIC FOR RESUBMISSIONS ---

        # 1. Save the new file to the correct temporary directory inside MEDIA_ROOT
        temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = os.path.join(temp_dir, new_file.name)
        with open(temp_file_path, 'wb+') as destination:
            for chunk in new_file.chunks():
                destination.write(chunk)

        # 2. Get the relative path to store in the database
        relative_path_for_db = os.path.join("temp_uploads", new_file.name).replace('\\', '/')

        with connections['default'].cursor() as cursor:
            # 3. Update the review_tasks record with the new temporary file info, reset the status, and clear the old evidence link.
            cursor.execute("""
                UPDATE review_tasks
                SET 
                    status = 'Pending', 
                    feedback = NULL, 
                    is_resubmission = 1, 
                    resubmitted_at = %s,
                    evidence_temp_name = %s,
                    evidence_temp_path = %s,
                    description = %s,
                    evidence_id = NULL
                WHERE id = %s
            """, [timezone.now(), new_file.name, relative_path_for_db, resubmit_description, task_id])

            # Log the resubmission event
            log_audit(
                username,
                "Resubmitted Evidence",
                new_file.name,
                f"User resubmitted evidence for task ID: {task_id}"
            )

        return redirect('tasks')

    # For a GET request, show the form with the original feedback
    return render(request, "competency/resubmit_form.html", {
        "task_id": task_id,
        "feedback": feedback
    })


@login_required
def view_feedback(request, task_id):
    """
    Shows a user the feedback for a rejected task.
    This version is updated to work with the new submission workflow.
    """
    username = request.user.username

    with connections['default'].cursor() as cursor:
        cursor.execute("""
            SELECT 
                COALESCE(E.name, R.evidence_temp_name) AS file_name,
                COALESCE(E.file_path, R.evidence_temp_path) AS file_path,
                COALESCE(E.description, R.description) AS description,
                R.feedback,
                R.status
            FROM review_tasks R
            LEFT JOIN evidence E ON R.evidence_id = E.id
            WHERE R.id = %s AND COALESCE(E.username, R.username) = %s
        """, [task_id, username])
        row = cursor.fetchone()

        if not row:
            return HttpResponse("Feedback not found or you do not have permission to view it.", status=404)

        file_name, file_path, description, feedback, status = row

    context = {
        "file_name": file_name,
        "file_path": file_path,
        "description": description,
        "feedback": feedback,
        "status": status,
        "task_id": task_id
    }
    return render(request, "competency/view_feedback.html", context)


def submissions(request):
    return render(request, "competency/submissions.html")


@login_required
def messages(request):
    username = request.user.username

    with connections['default'].cursor() as cursor:
        cursor.execute("""
            SELECT timestamp, action, target, details
            FROM messages_audit
            WHERE username = %s
            ORDER BY timestamp DESC
        """, [username])
        messages = cursor.fetchall()

    return render(request, "competency/messages.html", {
        "messages": messages
    })


@login_required
def create_submission(request):
    user = request.user
    employee_id = get_employee_id_from_user(user)
    message = None
    error = None

    if not employee_id:
        return HttpResponse("Employee record not found.")

    # Fetch competencies for the dropdown.
    # We now fetch BOTH the ID and the NAME.
    competencies_for_dropdown = []
    with connections['default'].cursor() as cursor:
        cursor.execute("""
            SELECT c.competency_id, c.name 
            FROM dbo.competency_user cu
            JOIN dbo.competencies c ON cu.competency_id = c.competency_id
            WHERE cu.employee_id = %s
        """, [employee_id])
        competencies_for_dropdown = cursor.fetchall()

    # Fetch assessors
    with connections['competency_db'].cursor() as cursor:
        cursor.execute("SELECT Name FROM dbo.LineManagers")
        assessors = [row[0] for row in cursor.fetchall()]

    if request.method == "POST":
        uploaded_files = request.FILES.getlist("evidence_files")
        description = request.POST.get("description", "")
        username = user.username
        selected_assessor = request.POST.get("assessor")
        # The form will now submit the competency's ID, not its name.
        selected_competency_id = request.POST.get("competency")

        if uploaded_files and selected_competency_id:
            for uploaded_file in uploaded_files:
                temp_dir = os.path.join(settings.MEDIA_ROOT, "temp_uploads")
                os.makedirs(temp_dir, exist_ok=True)
                temp_file_path = os.path.join(temp_dir, uploaded_file.name)

                with open(temp_file_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)

                relative_path_for_db = os.path.join("temp_uploads", uploaded_file.name).replace('\\', '/')

                with connections['default'].cursor() as cursor:
                    # The INSERT statement now uses the new competency_id column.
                    cursor.execute("""
                        INSERT INTO review_tasks (assessor_name, status, assigned_at, 
                                                  evidence_temp_name, evidence_temp_path, 
                                                  description, username, competency_id)
                        VALUES (%s, 'Pending', %s, %s, %s, %s, %s, %s)
                    """, [selected_assessor, timezone.now(), uploaded_file.name,
                          relative_path_for_db, description, username, selected_competency_id])

                    # Find the competency name again just for the audit log
                    with connections['default'].cursor() as log_cursor:
                        log_cursor.execute("SELECT name FROM dbo.competencies WHERE competency_id = %s", [selected_competency_id])
                        log_comp_name = log_cursor.fetchone()[0]
                        log_audit(username, "Submitted Evidence", uploaded_file.name, log_comp_name)

            file_count = len(uploaded_files)
            message = f"{file_count} submission(s) successfully uploaded and sent for review."
        else:
            error = "You must select a competency and attach at least one file."

    context = {
        # Pass the list of (id, name) tuples to the template
        "competencies": competencies_for_dropdown,
        "assessors": assessors,
        "message": message,
        "error": error,
        "is_line_manager": request.session.get("is_line_manager", False)
    }
    return render(request, "competency/create_submission.html", context)


@login_required
def team_dashboard(request):
    """
    Line managers can view the competency status of their team.
    This version adds a pending task count for each team member for the table layout.
    """
    try:
        manager_employee_id = get_employee_id_from_user(request.user)
        if not manager_employee_id:
            return HttpResponse("Could not identify the employee record for the logged-in user.")

        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT FirstName, LastName FROM dbo.Emps_GO WHERE id = %s", [manager_employee_id])
            row = cursor.fetchone()
            if not row:
                return HttpResponse("Could not find manager details.")
            manager_full_name = f"{row[0]} {row[1]}"

    except Exception as e:
        return HttpResponse(f"An error occurred while identifying the user: {e}")

    try:
        with connections['competency_db'].cursor() as cursor:
            cursor.execute("SELECT Id FROM dbo.LineManagers WHERE Name = %s", [manager_full_name])
            manager_row = cursor.fetchone()
            if not manager_row:
                return render(request, "competency/team_dashboard.html", {"team": {}})
            line_manager_id_for_query = manager_row[0]

    except Exception as e:
        return HttpResponse(f"Database error verifying manager permissions: {e}")

    try:
        with connections['default'].cursor() as cursor:
            cursor.execute("""
                SELECT 
                    E.Id, E.FirstName, E.LastName,
                    C.name AS competency_name, -- Changed: Get name from the competencies table
                    CU.status
                FROM dbo.Emps_GO E
                LEFT JOIN dbo.competency_user CU ON E.Id = CU.employee_id
                LEFT JOIN dbo.competencies C ON CU.competency_id = C.competency_id -- Added: New JOIN
                WHERE E.LineManagerId = %s
                ORDER BY E.LastName, E.FirstName
            """, [line_manager_id_for_query])
            results = cursor.fetchall()
    except Exception as e:
        # The original error message you saw came from this block
        return HttpResponse(f"Database error fetching team data: {e}")

    # The rest of your data processing logic remains the same
    team_data = {}
    total_competencies = 0
    total_approved = 0
    total_pending_reviews = 0

    for emp_id, first, last, comp, status in results:
        name = f"{first} {last}"
        if emp_id not in team_data:
            team_data[emp_id] = {"name": name, "competencies": [], "pending_count": 0}
        if comp:
            team_data[emp_id]["competencies"].append({"name": comp, "status": status})

    for emp_id, data in team_data.items():
        num_competencies = len(data["competencies"])
        num_approved = sum(1 for c in data["competencies"] if c.get('status') == 'Approved')
        num_pending_local = sum(1 for c in data["competencies"] if c.get('status') == 'Pending')
        data['pending_count'] = num_pending_local
        data['progress'] = round((num_approved / num_competencies) * 100) if num_competencies > 0 else 0

        total_competencies += num_competencies
        total_approved += num_approved
        total_pending_reviews += num_pending_local

    overall_team_progress = round((total_approved / total_competencies) * 100) if total_competencies > 0 else 0

    context = {
        "team": team_data,
        "total_team_members": len(team_data),
        "total_pending_reviews": total_pending_reviews,
        "overall_team_progress": overall_team_progress,
        "is_line_manager": request.session.get("is_line_manager", False)
    }

    return render(request, "competency/team_dashboard.html", context)


def log_audit(username, action, subject, details):
    # This is a placeholder for your existing audit logging function
    print(f"AUDIT | User: {username}, Action: {action}, Subject: {subject}, Details: {details}")
    pass


@login_required
def assign_competency(request):
    """
    Allows a manager to define a new competency and its objectives,
    and assign it to team members in a single form.
    """
    if not request.session.get("is_line_manager"):
        return HttpResponse("You do not have permission to access this page.", status=403)

    manager_employee_id = get_employee_id_from_user(request.user)

    # --- REAL LOGIC TO FETCH TEAM MEMBERS ---
    team_members = []
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT FirstName, LastName FROM dbo.Emps_GO WHERE id = %s", [manager_employee_id])
            manager_row = cursor.fetchone()
            manager_full_name = f"{manager_row[0]} {manager_row[1]}" if manager_row else ""

        with connections['competency_db'].cursor() as cursor:
            cursor.execute("SELECT Id FROM dbo.LineManagers WHERE Name = %s", [manager_full_name])
            lm_row = cursor.fetchone()
            if lm_row:
                line_manager_id_for_query = lm_row[0]
                with connections['default'].cursor() as cursor:
                    cursor.execute("SELECT id, FirstName, LastName FROM dbo.Emps_GO WHERE LineManagerId = %s",
                                   [line_manager_id_for_query])
                    for row in cursor.fetchall():
                        team_members.append({'id': row[0], 'name': f"{row[1]} {row[2]}"})
    except Exception as e:
        return HttpResponse(f"A database error occurred while fetching team members: {e}")
    # --- END OF TEAM MEMBER LOGIC ---

    if request.method == "POST":
        try:
            # --- Get all data from the form ---
            selected_member_ids = request.POST.getlist("team_members")
            assessment_date = request.POST.get("assessment_date")
            new_competency_name = request.POST.get("new_competency_name")
            new_objectives = request.POST.getlist("new_objectives")
            criteria_data = json.loads(request.POST.get("criteria_data"))

            if not all([selected_member_ids, assessment_date, new_competency_name, new_objectives, criteria_data]):
                # Add error handling here if needed
                return HttpResponse("Form is incomplete.", status=400)

            with transaction.atomic():
                with connections['default'].cursor() as cursor:
                    # 1. Create the new CompetencyTemplate record
                    cursor.execute(
                        "INSERT INTO dbo.Competencies (name, version, is_active) OUTPUT INSERTED.competency_id VALUES (%s, '1.0', 1)",
                        [new_competency_name])
                    template_id = cursor.fetchone()[0]

                    # 2. Create the Objective records for the new template
                    for i, objective_text in enumerate(new_objectives):
                        if objective_text:
                            cursor.execute(
                                "INSERT INTO dbo.Objectives (template_id, objective_text, sort_order) VALUES (%s, %s, %s)",
                                [template_id, objective_text, i])

                    log_audit(request.user.username, "Created Competency", new_competency_name,
                              f"{len(new_objectives)} objectives added.")

                    # 3. Create the review records for each employee
                    for member_id in selected_member_ids:
                        cursor.execute(
                            "INSERT INTO dbo.CompetencyReviews (template_id, employee_id, assessor_id, assessment_date, overall_outcome) OUTPUT INSERTED.id VALUES (%s, %s, %s, %s, 'Recorded')",
                            [template_id, member_id, manager_employee_id, assessment_date])
                        review_id = cursor.fetchone()[0]

                        for criterion in criteria_data:
                            cursor.execute(
                                "INSERT INTO dbo.ReviewEvidence (review_id, objective_text, result, evidence_notes) VALUES (%s, %s, %s, %s)",
                                [review_id, criterion['objectiveText'], criterion['result'], criterion['evidence']])

            log_audit(request.user.username, "Assigned Competency", new_competency_name,
                      f"Assigned to {len(selected_member_ids)} team member(s)")

            context = {
                'message': f"Competency '{new_competency_name}' was successfully recorded and assigned.",
                'team_members': team_members,
            }
            return render(request, 'competency/assign_competency.html', context)
        except Exception as e:
            return HttpResponse(f"An error occurred during submission: {e}", status=500)

    context = {
        'team_members': team_members,
    }
    return render(request, 'competency/assign_competency.html', context)

@login_required
def get_template_objectives(request):
    """
    AJAX endpoint to fetch the objectives for a given competency template.
    """
    template_id = request.GET.get('template_id')
    if not template_id:
        return JsonResponse({'error': 'Template ID is required'}, status=400)

    objectives = []
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute(
                "SELECT id, objective_text FROM dbo.Objectives WHERE template_id = %s ORDER BY sort_order",
                [template_id]
            )
            for row in cursor.fetchall():
                objectives.append({'id': row[0], 'text': row[1]})
    except Exception as e:
        return JsonResponse({'error': f'Database error: {e}'}, status=500)

    return JsonResponse({'objectives': objectives})

























