from django.urls import path
from . import views
from . import views_public

urlpatterns = [
    path('p/<str:employee_id>/<str:token>/', views_public.public_salary_slip, name='public_salary_slip'),
    path('', views.payroll_list, name='payroll_list'),
    path('create/', views.payroll_create, name='payroll_create'),
    path('<int:pk>/', views.payroll_detail, name='payroll_detail'),
    path('<int:pk>/edit/', views.payroll_update, name='payroll_update'),
    path('<int:pk>/delete/', views.payroll_delete, name='payroll_delete'),
    path('<int:pk>/process/', views.payroll_process, name='payroll_process'),
    path('<int:pk>/slip/', views.salary_slip, name='salary_slip'),
    path('<int:pk>/slip/pdf/', views.salary_slip_pdf, name='salary_slip_pdf'),
    path('export/', views.payroll_export, name='payroll_export'),
    path('summary/', views.payroll_summary, name='payroll_summary'),
    path('auto-generate/', views.auto_generate_payroll, name='auto_generate_payroll'),
    path('policy/', views.policy_list, name='policy_list'),
    path('policy/create/', views.policy_create, name='policy_create'),
    path('policy/<int:pk>/edit/', views.policy_update, name='policy_update'),
    path('policy/<int:pk>/activate/', views.policy_activate, name='policy_activate'),
    path('boutique/products/', views.boutique_product_list, name='boutique_product_list'),
    path('boutique/products/add/', views.boutique_product_create, name='boutique_product_create'),
    path('boutique/products/<int:pk>/edit/', views.boutique_product_edit, name='boutique_product_edit'),
    path('boutique/products/<int:pk>/delete/', views.boutique_product_delete, name='boutique_product_delete'),
    path('boutique/issues/', views.boutique_issue_list, name='boutique_issue_list'),
    path('boutique/issues/add/', views.boutique_issue_create, name='boutique_issue_create'),
    path('loans/', views.loan_list, name='loan_list'),
    path('loans/create/', views.loan_create, name='loan_create'),
    path('department-salary/', views.department_salary, name='department_salary'),
]
