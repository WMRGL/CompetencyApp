from django.db import models


class EmpsSynonym(models.Model):
    id = models.AutoField(primary_key=True)
    emp_no = models.CharField(db_column="EmpNo", max_length=50)
    first_name = models.CharField(db_column="FirstName", max_length=255)
    middle_name = models.CharField(db_column="MiddleName", max_length=255, null=True, blank=True)
    last_name = models.CharField(db_column="LastName", max_length=255)
    phone_number = models.CharField(db_column="PhoneNumber", max_length=50, null=True, blank=True)
    mandatory_training = models.BooleanField(db_column="MandatoryTraining", null=True, blank=True)
    email_address = models.EmailField(db_column="EmailAddress", max_length=255, null=True, blank=True)
    start_date = models.DateField(db_column="StartDate", null=True, blank=True)
    end_date = models.DateField(db_column="Enddate", null=True, blank=True)
    is_active = models.BooleanField(db_column="IsActive", null=True, blank=True)
    dept_id = models.IntegerField(db_column="DeptId", null=True, blank=True)
    role_id = models.IntegerField(db_column="RoleId", null=True, blank=True)
    team_id = models.IntegerField(db_column="TeamId", null=True, blank=True)
    line_manager_id = models.IntegerField(db_column="LineManagerId", null=True, blank=True)

    class Meta:
        managed = False
        db_table = '[dbo].[Emps_GO]'
        app_label = 'competency'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.emp_no})"


class Competencies(models.Model):
    competency_id = models.AutoField(primary_key=True, db_column='competency_id')
    name = models.CharField(max_length=255)
    description = models.TextField()

    class Meta:
        db_table = '[dbo].[competencies]'
        app_label = 'competency'

    def __str__(self):
        return self.name


class CompetencyUser(models.Model):
    employee = models.ForeignKey(
        'EmpsSynonym',
        db_column='employee_id',
        on_delete=models.DO_NOTHING
    )
    competency = models.ForeignKey(
        'Competencies',
        db_column='competency_id',
        on_delete=models.DO_NOTHING
    )
    progress = models.IntegerField()
    status = models.CharField(max_length=50)

    class Meta:
        db_table = '[dbo].[competency_user]'
        managed = False
        app_label = 'competency'

    def __str__(self):
        return f"{self.employee} - {self.competency} ({self.status}, {self.progress}%)"


class Evidence(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    file_path = models.TextField()
    description = models.TextField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '[dbo].[evidence]'
        app_label = 'competency'


class CompetencyRoles(models.Model):
    competency = models.ForeignKey(
        'Competencies', on_delete=models.CASCADE, db_column='competency_id'
    )
    job_title = models.CharField(max_length=255)

    class Meta:
        db_table = '[dbo].[competency_roles]'
        app_label = 'competency'
        unique_together = ('competency', 'job_title')














