from locust import HttpUser, task, between
#limiter limits it so to test change discover limiter to higher number than change back
#to test run locust --host=http://127.0.0.1:5000 command in seperate terminal while running application
class MeetingPointUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def visit_discover(self):
        self.client.get('/discover')

    @task(2)
    def search_events(self):
        self.client.get('/discover?q=tbilisi&category=social')

    @task(1)
    def visit_home(self):
        self.client.get('/')

    @task(1)
    def visit_event(self):
        self.client.get('/events/35')