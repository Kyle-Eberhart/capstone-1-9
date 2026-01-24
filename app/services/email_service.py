"""Email service for sending notifications using SendGrid API."""
import html
from typing import Optional
import logging
from app.settings import get_settings

logger = logging.getLogger(__name__)

# Try to import SendGrid, but handle gracefully if not installed
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.warning("SendGrid library not installed. Run: pip install sendgrid")


class EmailService:
    """Service for sending emails via SendGrid API."""
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
    
    def _get_client(self):
        """Get or create SendGrid client."""
        if not SENDGRID_AVAILABLE:
            return None
        
        if self._client is None and self.settings.sendgrid_api_key:
            try:
                self._client = SendGridAPIClient(self.settings.sendgrid_api_key)
            except Exception as e:
                logger.error(f"Failed to initialize SendGrid client: {e}")
                return None
        
        return self._client
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> bool:
        """Send an email using SendGrid API.
        
        Args:
            to_email: Recipient email address (any email provider)
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional)
        
        Returns:
            True if email sent successfully, False otherwise
        """
        # Check if SendGrid is configured
        if not self.settings.sendgrid_api_key:
            logger.warning(
                f"Email not configured - SendGrid API key missing. "
                f"Add SENDGRID_API_KEY to your .env file. "
                f"Skipping email send to {to_email}."
            )
            return False
        
        if not SENDGRID_AVAILABLE:
            logger.error(
                "SendGrid library not installed. Install with: pip install sendgrid"
            )
            return False
        
        client = self._get_client()
        if not client:
            logger.error("Failed to initialize SendGrid client")
            return False
        
        try:
            # Create email message
            from_email = Email(
                self.settings.email_from_address,
                self.settings.email_from_name
            )
            to_email_obj = Email(to_email)
            
            # Create content
            html_content = Content("text/html", html_body)
            
            # Create mail message
            message = Mail(
                from_email=from_email,
                to_emails=to_email_obj,
                subject=subject,
                html_content=html_content
            )
            
            # Add text content if provided (SendGrid handles multipart automatically)
            if text_body:
                text_content = Content("text/plain", text_body)
                message.add_content(text_content)
            
            # Send email
            response = client.send(message)
            
            # Check response status
            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully to {to_email}: {subject}")
                return True
            else:
                logger.error(
                    f"SendGrid API returned status {response.status_code} when sending to {to_email}. "
                    f"Response: {response.body}"
                )
                return False
                
        except Exception as e:
            logger.error(
                f"Error sending email to {to_email} via SendGrid: {e}. "
                f"Check your SENDGRID_API_KEY in .env file.",
                exc_info=True
            )
            return False
    
    def send_dispute_notification(
        self,
        to_email: str,
        student_name: str,
        course_number: str,
        exam_name: str,
        exam_details_html: str
    ) -> bool:
        """Send grade dispute notification email to instructor.
        
        Args:
            to_email: Instructor email address (any email provider)
            student_name: Student's name
            course_number: Course number
            exam_name: Exam name
            exam_details_html: HTML content of exam details
        
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = f"{student_name} {course_number} {exam_name} GRADE DISPUTED"
        
        html_body = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #fff3cd;
                    border-left: 4px solid #ff9800;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }}
                .header h1 {{
                    margin: 0;
                    color: #856404;
                }}
                .content {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚠️ Grade Dispute Notification</h1>
                    <p><strong>Subject:</strong> {subject}</p>
                </div>
                <div class="content">
                    {exam_details_html}
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
Grade Dispute Notification

Subject: {subject}

A student has disputed their grade. Please review the exam details in the application.

Student: {student_name}
Course: {course_number}
Exam: {exam_name}

Please log in to the application to view full details and the student's dispute reason.
        """
        
        return self.send_email(to_email, subject, html_body, text_body)
    
    def generate_exam_details_html(
        self,
        exam,
        student_name: str,
        questions: list,
        dispute_reason: Optional[str] = None
    ) -> str:
        """Generate HTML content for exam details email.
        
        Args:
            exam: Exam object
            student_name: Student's name
            questions: List of Question objects
            dispute_reason: Optional dispute reason
        
        Returns:
            HTML string with exam details
        """
        from datetime import datetime
        
        def format_datetime(dt):
            if dt:
                return dt.strftime('%m/%d/%Y %I:%M %p')
            return 'N/A'
        
        # Build dispute notice if disputed
        dispute_section = ""
        if dispute_reason:
            dispute_section = f"""
            <div style="background-color: #fff3cd; border-left: 4px solid #ff9800; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <h2 style="margin-top: 0; color: #856404;">⚠️ Grade Disputed</h2>
                <p style="color: #856404; margin-bottom: 10px;"><strong>This exam grade has been disputed by the student.</strong></p>
                <div style="background-color: white; padding: 15px; border-radius: 4px; margin-top: 10px;">
                    <strong style="color: #856404;">Student's Reason:</strong>
                    <p style="color: #333; margin-top: 8px; white-space: pre-wrap;">{html.escape(dispute_reason)}</p>
                </div>
            </div>
            """
        
        # Build exam information section
        status_badge = ""
        if exam.status == 'active':
            status_badge = '<span style="background-color: #4CAF50; color: white; padding: 5px 12px; border-radius: 12px; font-size: 0.85em;">Active</span>'
        elif exam.status == 'completed':
            status_badge = '<span style="background-color: #2196F3; color: white; padding: 5px 12px; border-radius: 12px; font-size: 0.85em;">Completed</span>'
        elif exam.status == 'disputed':
            status_badge = '<span style="background-color: #ff9800; color: white; padding: 5px 12px; border-radius: 12px; font-size: 0.85em;">Disputed</span>'
        elif exam.status == 'not_started':
            status_badge = '<span style="background-color: #ff9800; color: white; padding: 5px 12px; border-radius: 12px; font-size: 0.85em;">Not Started</span>'
        else:
            status_badge = '<span style="background-color: #9e9e9e; color: white; padding: 5px 12px; border-radius: 12px; font-size: 0.85em;">Draft</span>'
        
        exam_info_html = f"""
        <div style="background-color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h2 style="margin-top: 0; color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">Exam Information</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666; width: 200px;">Exam ID</td>
                    <td style="padding: 10px; color: #333;">{html.escape(exam.exam_id)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666;">Course Number</td>
                    <td style="padding: 10px; color: #333;">{html.escape(exam.course_number)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666;">Section</td>
                    <td style="padding: 10px; color: #333;">{html.escape(exam.section)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666;">Quarter / Year</td>
                    <td style="padding: 10px; color: #333;">{html.escape(exam.quarter_year)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666;">Exam Name</td>
                    <td style="padding: 10px; color: #333;">{html.escape(exam.exam_name)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666;">Student</td>
                    <td style="padding: 10px; color: #333;">{html.escape(student_name)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666;">Status</td>
                    <td style="padding: 10px; color: #333;">{status_badge}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666;">Final Grade</td>
                    <td style="padding: 10px; color: #333;">{f'{exam.final_grade * 100:.1f}%' if exam.final_grade else 'N/A'}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; background-color: #f8f9fa; font-weight: 600; color: #666;">Completed At</td>
                    <td style="padding: 10px; color: #333;">{format_datetime(exam.completed_at)}</td>
                </tr>
            </table>
        </div>
        """
        
        # Build questions section
        questions_html = ""
        if questions:
            questions_html = '<div style="background-color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;"><h2 style="margin-top: 0; color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">Questions and Answers</h2>'
            for question in sorted(questions, key=lambda q: q.question_number):
                grade_display = f'{question.grade * 100:.1f}%' if question.grade is not None else 'Not graded yet'
                grade_color = '#4CAF50' if question.grade is not None else '#999'
                
                questions_html += f"""
                <div style="margin-bottom: 30px; padding: 20px; background-color: #f8f9fa; border-radius: 8px; border-left: 4px solid #4CAF50;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <h3 style="margin: 0; color: #333;">Question {question.question_number}</h3>
                        <div style="font-size: 1.2em; font-weight: 600; color: {grade_color};">
                            Grade: {grade_display}
                        </div>
                    </div>
                    <div style="margin-bottom: 15px;">
                        <strong style="color: #666; display: block; margin-bottom: 5px;">Question:</strong>
                        <div style="padding: 12px; background-color: white; border-radius: 4px; color: #333;">
                            {html.escape(question.question_text)}
                        </div>
                    </div>
                """
                
                if question.context:
                    questions_html += f"""
                    <div style="margin-bottom: 15px;">
                        <strong style="color: #666; display: block; margin-bottom: 5px;">Context:</strong>
                        <div style="padding: 12px; background-color: white; border-radius: 4px; color: #666; font-size: 0.95em;">
                            {html.escape(question.context)}
                        </div>
                    </div>
                    """
                
                if question.rubric:
                    questions_html += f"""
                    <div style="margin-bottom: 15px;">
                        <strong style="color: #666; display: block; margin-bottom: 5px;">Rubric:</strong>
                        <div style="padding: 12px; background-color: white; border-radius: 4px; color: #666; font-size: 0.95em;">
                            {html.escape(question.rubric)}
                        </div>
                    </div>
                    """
                
                if question.student_answer:
                    questions_html += f"""
                    <div style="margin-bottom: 15px;">
                        <strong style="color: #666; display: block; margin-bottom: 5px;">Student Answer:</strong>
                        <div style="padding: 12px; background-color: #e7f3ff; border-radius: 4px; color: #333; white-space: pre-wrap; word-wrap: break-word;">
                            {html.escape(question.student_answer)}
                        </div>
                    </div>
                    """
                
                if question.feedback:
                    questions_html += f"""
                    <div style="margin-bottom: 15px;">
                        <strong style="color: #666; display: block; margin-bottom: 5px;">Feedback:</strong>
                        <div style="padding: 12px; background-color: white; border-radius: 4px; color: #333;">
                            {html.escape(question.feedback)}
                        </div>
                    </div>
                    """
                
                questions_html += "</div>"
            
            questions_html += "</div>"
        
        # Combine all sections
        full_html = f"""
        {dispute_section}
        {exam_info_html}
        {questions_html}
        """
        
        return full_html
