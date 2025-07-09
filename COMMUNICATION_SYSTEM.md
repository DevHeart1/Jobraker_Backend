# Communication System Documentation

## Overview

The Jobraker backend includes a comprehensive communication system that handles email notifications, job alerts, application status updates, and real-time chat functionality.

## Components

### 1. Email Service (`apps/notifications/email_service.py`)

The `EmailService` class provides a unified interface for sending various types of emails:

- **Job Alerts**: Automated notifications about new job matches
- **Application Status Updates**: Notifications when application status changes
- **Welcome Emails**: Sent to new users upon registration
- **Job Recommendations**: Weekly personalized job suggestions
- **Follow-up Reminders**: Reminders for pending applications
- **Password Reset**: Secure password reset emails

#### Features:
- HTML email templates with fallback to plain text
- Bulk email sending capabilities
- Template-based email generation
- Retry logic for failed sends
- Support for attachments

### 2. Email Templates (`templates/emails/`)

Professional HTML email templates:
- `base.html`: Base template with consistent styling
- `job_alert.html`: Job alert notifications
- `application_status_update.html`: Application status changes
- `welcome.html`: Welcome email for new users
- `password_reset.html`: Password reset instructions
- `job_recommendations.html`: Personalized job recommendations
- `application_follow_up.html`: Follow-up reminders

### 3. Celery Tasks (`apps/notifications/tasks.py`)

Asynchronous email processing:
- `send_job_alert_email_task`: Send job alerts to users
- `send_application_status_update_task`: Send status updates
- `send_welcome_email_task`: Send welcome emails
- `send_job_recommendations_task`: Send recommendations
- `send_follow_up_reminder_task`: Send follow-up reminders
- `process_daily_job_alerts`: Process all daily alerts
- `process_weekly_job_alerts`: Process weekly alerts
- `send_weekly_job_recommendations`: Send weekly recommendations
- `send_application_follow_up_reminders`: Send follow-up reminders

### 4. Django Signals (`apps/notifications/signals.py`)

Automatic email triggers:
- New user registration → Welcome email
- Application status change → Status update email

### 5. WebSocket Support (`apps/chat/`)

Real-time communication features:
- **Chat Consumer**: Real-time chat with AI assistant
- **Notification Consumer**: Real-time notifications
- **WebSocket Routing**: URL patterns for WebSocket connections

## Configuration

### Email Settings

Add these settings to your `.env` file:

```env
# Email Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@jobraker.com
SERVER_EMAIL=noreply@jobraker.com
ADMIN_EMAIL=admin@jobraker.com
SUPPORT_EMAIL=support@jobraker.com
COMPANY_NAME=Jobraker
SITE_URL=https://jobraker.com
```

### SMTP Providers

#### Gmail
```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

#### SendGrid
```env
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key
```

#### AWS SES
```env
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-aws-access-key
EMAIL_HOST_PASSWORD=your-aws-secret-key
```

### WebSocket Configuration

WebSocket support is automatically configured with Redis:

```python
# Channel layer configuration
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [os.getenv('REDIS_URL', 'redis://localhost:6379/0')],
        },
    },
}
```

## Usage

### Sending Emails Programmatically

```python
from apps.notifications.email_service import EmailService

email_service = EmailService()

# Send welcome email
email_service.send_welcome_email(user)

# Send job recommendations
email_service.send_job_recommendation_email(user, recommendations)

# Send custom email
email_service.send_email(
    subject="Custom Email",
    template_name="custom_template",
    context={'user': user, 'data': data},
    recipient_list=[user.email]
)
```

### Using Celery Tasks

```python
from apps.notifications.tasks import send_welcome_email_task

# Send welcome email asynchronously
send_welcome_email_task.delay(user_id)
```

### WebSocket Usage

#### Client-side JavaScript

```javascript
// Connect to chat
const chatSocket = new WebSocket(
    'ws://' + window.location.host + '/ws/chat/' + sessionId + '/'
);

chatSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    if (data.type === 'message') {
        displayMessage(data.message);
    }
};

// Send message
chatSocket.send(JSON.stringify({
    'type': 'message',
    'message': 'Hello!'
}));

// Connect to notifications
const notificationSocket = new WebSocket(
    'ws://' + window.location.host + '/ws/notifications/'
);

notificationSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    if (data.type === 'notification') {
        showNotification(data.notification);
    }
};
```

## Scheduled Tasks

The system includes several scheduled tasks configured in `jobraker/celery.py`:

- **Daily Job Alerts**: 9:00 AM UTC
- **Weekly Job Alerts**: Monday 9:00 AM UTC
- **Weekly Recommendations**: Monday 10:00 AM UTC
- **Follow-up Reminders**: 11:00 AM UTC daily

## Testing

### Test Email Functionality

```bash
# Test all email types
python manage.py test_email --test-type all

# Test welcome email
python manage.py test_email --test-type welcome --user-email user@example.com

# Test recommendations
python manage.py test_email --test-type recommendations --user-email user@example.com

# Test job alerts
python manage.py test_email --test-type job-alerts
```

### Test WebSocket Connections

Use a WebSocket client or browser dev tools to test:

```javascript
// Test chat connection
const ws = new WebSocket('ws://localhost:8000/ws/chat/test-session/');

// Test notification connection
const notifWs = new WebSocket('ws://localhost:8000/ws/notifications/');
```

## Production Deployment

### Requirements

1. **Redis**: Required for Celery and WebSocket support
2. **SMTP Server**: For email delivery
3. **Celery Workers**: For background task processing
4. **Celery Beat**: For scheduled tasks

### Deployment Commands

```bash
# Start Celery worker
celery -A jobraker worker --loglevel=info

# Start Celery beat scheduler
celery -A jobraker beat --loglevel=info

# Start Django with ASGI support
daphne jobraker.asgi:application
```

### Docker Compose Example

```yaml
version: '3.8'

services:
  web:
    build: .
    command: daphne jobraker.asgi:application
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - postgres

  celery:
    build: .
    command: celery -A jobraker worker --loglevel=info
    depends_on:
      - redis
      - postgres

  celery-beat:
    build: .
    command: celery -A jobraker beat --loglevel=info
    depends_on:
      - redis
      - postgres

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: jobraker_db
      POSTGRES_USER: jobraker_user
      POSTGRES_PASSWORD: jobraker_pass
```

## Monitoring

### Email Delivery Monitoring

- Check Django logs for email send success/failure
- Monitor SMTP server metrics
- Track email open/click rates (requires additional setup)

### WebSocket Monitoring

- Monitor Redis connection count
- Track WebSocket connection metrics
- Monitor chat message volume

### Celery Monitoring

Use Celery monitoring tools:

```bash
# Celery monitoring
celery -A jobraker inspect active
celery -A jobraker inspect scheduled
celery -A jobraker inspect stats
```

## Security Considerations

1. **Email Security**:
   - Use app-specific passwords for Gmail
   - Enable 2FA for email accounts
   - Use environment variables for credentials

2. **WebSocket Security**:
   - Authentication required for connections
   - Rate limiting on messages
   - Input validation and sanitization

3. **SMTP Security**:
   - Use TLS/SSL for SMTP connections
   - Avoid storing passwords in code
   - Regular credential rotation

## Troubleshooting

### Common Issues

1. **Email not sending**:
   - Check SMTP credentials
   - Verify email backend configuration
   - Check Django logs for errors

2. **WebSocket connection failures**:
   - Ensure Redis is running
   - Check ASGI configuration
   - Verify channel layer settings

3. **Celery tasks not processing**:
   - Check Redis connection
   - Verify Celery worker is running
   - Check task queue status

### Debug Commands

```bash
# Check email configuration
python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail('Test', 'Test message', 'from@example.com', ['to@example.com'])

# Check Celery connection
python manage.py shell
>>> from celery import current_app
>>> current_app.control.ping()

# Check Redis connection
python manage.py shell
>>> import redis
>>> r = redis.Redis(host='localhost', port=6379, db=0)
>>> r.ping()
```

## API Endpoints

The communication system also provides API endpoints for managing notifications:

- `GET /api/notifications/`: List user notifications
- `POST /api/notifications/mark-read/`: Mark notifications as read
- `GET /api/chat/sessions/`: List chat sessions
- `POST /api/chat/sessions/`: Create new chat session
- `GET /api/chat/sessions/{id}/messages/`: Get chat messages
- `POST /api/chat/sessions/{id}/messages/`: Send chat message

## Future Enhancements

1. **Push Notifications**: Mobile app push notifications
2. **Email Templates**: More customizable email templates
3. **SMS Notifications**: Text message alerts
4. **Webhook Support**: External system integrations
5. **Email Analytics**: Open/click tracking
6. **Multi-language Support**: Internationalized emails
7. **Advanced Chat Features**: File sharing, voice messages
