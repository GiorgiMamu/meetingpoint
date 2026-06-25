# MeetingPoint — API Endpoint Documentation

All endpoints follow RESTful conventions. HTML responses are returned for browser requests.
Authentication is session-based (Flask-Login). CSRF protection is enforced on all POST/DELETE forms.

---

## Authentication

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/register` | Registration page | No |
| POST | `/register` | Create new account | No |
| GET | `/login` | Login page | No |
| POST | `/login` | Authenticate user | No |
| GET | `/logout` | Log out current user | Yes |
| GET | `/confirm/<token>` | Confirm email address | No |
| GET | `/reset-password` | Password reset request page | No |
| POST | `/reset-password` | Send password reset email | No |
| GET | `/reset-password/<token>` | Password reset form | No |
| POST | `/reset-password/<token>` | Set new password | No |

---

## Events

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/discover` | Browse public events with filters | No |
| GET | `/discover/recommended` | Personalised event recommendations | No |
| GET | `/events/create` | Event creation form | Yes |
| POST | `/events/create` | Create new event | Yes |
| GET | `/events/<id>` | Event detail page | No* |
| GET | `/events/<id>/edit` | Edit event form | Yes (host) |
| POST | `/events/<id>/edit` | Update event | Yes (host) |
| POST | `/events/<id>/delete` | Delete event | Yes (host/admin) |
| POST | `/events/<id>/cancel` | Cancel event | Yes (host) |
| POST | `/events/<id>/join` | Join event | Yes |
| POST | `/events/<id>/leave` | Leave event | Yes |
| POST | `/events/<id>/bookmark` | Toggle bookmark | Yes |
| GET | `/events/<id>/share` | Share event page | Yes (host) |
| POST | `/events/<id>/share-to-follower/<id>` | Invite follower | Yes (host) |
| GET | `/events/<id>/chat` | Event chat page | Yes (participant/host) |
| GET | `/events/<id>/report` | Report event form | Yes |
| POST | `/events/<id>/report` | Submit event report | Yes |

*Private events require authentication and participation/invitation

---

## Participant Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/events/<id>/approve/<user_id>` | Approve join request | Yes (host) |
| POST | `/events/<id>/decline/<user_id>` | Decline join request | Yes (host) |
| POST | `/events/<id>/remove/<user_id>` | Remove participant | Yes (host) |
| POST | `/events/<id>/invite/<user_id>` | Invite user to event | Yes (host) |

---

## Profiles & Social

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/profile/<id>` | View user profile | No* |
| GET | `/profile/edit` | Edit profile form | Yes |
| POST | `/profile/edit` | Update profile | Yes |
| GET | `/profile/<id>/followers` | View followers list | No* |
| GET | `/profile/<id>/following` | View following list | No* |
| POST | `/users/<id>/follow` | Follow/unfollow user | Yes |
| GET | `/users/<id>/report` | Report user form | Yes |
| POST | `/users/<id>/report` | Submit user report | Yes |

*Private profiles require authentication

---

## Navigation Pages

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/` | Home page | No |
| GET | `/my-events` | Host's own events | Yes |
| GET | `/history` | Participation history | Yes |
| GET | `/bookmarks` | Saved bookmarks | Yes |
| GET | `/chats` | All event chats | Yes |
| GET | `/notifications` | All notifications | Yes |
| POST | `/notifications/mark-read` | Mark all as read | Yes |
| POST | `/notifications/clear` | Clear all notifications | Yes |
| GET | `/dashboard` | Host analytics dashboard | Yes |
| GET | `/dashboard/event/<id>` | Per-event analytics | Yes (host) |

---

## Admin Panel

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/admin/users` | List all users | Yes (admin) |
| POST | `/admin/users/<id>/toggle_block` | Block/unblock user | Yes (admin) |
| POST | `/admin/users/<id>/delete` | Delete user | Yes (admin) |
| GET | `/admin/events` | List all events | Yes (admin) |
| GET | `/admin/reports` | List all reports | Yes (admin) |
| GET | `/admin/reports/<id>` | Report detail | Yes (admin) |
| POST | `/admin/reports/<id>/update` | Update report status | Yes (admin) |
| GET | `/admin/logs` | System audit logs | Yes (admin) |
| GET | `/admin/logs/<id>` | Log detail | Yes (admin) |

---

## Static Pages

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/privacy` | Privacy policy | No |
| GET | `/terms` | Terms of service | No |

---

## HTTP Status Codes Used

| Code | Meaning                                        |
|------|------------------------------------------------|
| 200 | OK - page loaded successfully                  |
| 302 | Redirect - after form submission or auth check |
| 403 | Forbidden - insufficient permissions           |
| 404 | Not found - resource does not exist            |
| 429 | Too many requests - rate limit exceeded        |
| 500 | Internal server error - logged to AuditLog     |