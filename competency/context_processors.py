from django.db import connections


def is_line_manager(request):
    """
    Checks if the logged-in user is a line manager.
    """
    if not request.user.is_authenticated:
        return {'is_line_manager': False}

    # Use a session variable if it's already been set during login
    if 'is_line_manager' in request.session:
        return {'is_line_manager': request.session['is_line_manager']}

    # Fallback logic if the session variable isn't set
    try:
        email = request.user.email
        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT id FROM dbo.Emps_GO WHERE EmailAddress = %s", [email])
            row = cursor.fetchone()
            if not row:
                return {'is_line_manager': False}

            employee_id = row[0]

            # This logic seems to check if the user *is* a manager, not if they *have* one.
            # It checks if their employee_id appears in the LineManagerId column for others.
            cursor.execute("SELECT 1 FROM dbo.Emps_GO WHERE LineManagerId = %s", [employee_id])
            result = cursor.fetchone()
            is_manager = bool(result)
            request.session['is_line_manager'] = is_manager  # Store for next time
            return {'is_line_manager': is_manager}
    except Exception:
        return {'is_line_manager': False}


def task_notification_processor(request):
    """
    Adds the count of pending tasks to the context for every request.
    """
    if not request.user.is_authenticated:
        return {'pending_task_count': 0}

    is_manager = is_line_manager(request).get('is_line_manager', False)
    username = request.user.username
    full_name = request.user.get_full_name()
    task_count = 0

    try:
        with connections['default'].cursor() as cursor:
            if is_manager:
                # This query for managers is correct.
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM review_tasks
                    WHERE assessor_name = %s AND status = 'Pending'
                """, [full_name])
            else:

                # This query for users is now updated to correctly count rejected tasks.
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM review_tasks R
                    LEFT JOIN evidence E ON R.evidence_id = E.id
                    WHERE COALESCE(E.username, R.username) = %s AND R.status = 'Rejected'
                """, [username])

            result = cursor.fetchone()
            if result:
                task_count = result[0]
    except Exception:
        task_count = 0

    return {'pending_task_count': task_count}