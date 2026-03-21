import random
import string
from locust import HttpUser, task, between

class AuthUser(HttpUser):
    wait_time = between(1, 5)

    @task
    def login(self):
        # We simulate login with a mix of correct and incorrect credentials
        # to generate some errors/variability in the metrics.
        
        # Test users seeded from users.json
        usernames = ["admin", "testuser2", "user1", "user2", "nonexistent"]
        username = random.choice(usernames)
        
        if username == "admin":
            password = "admin123"
        elif username == "nonexistent":
            password = "wrongpassword"
        else:
            password = "user123" if "user" in username else "password"

        payload = {
            "username": username,
            "password": password
        }
        
        with self.client.post("/login", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                # 401 is expected for "nonexistent" user
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code}")

    @task(3)
    def health_check(self):
        self.client.get("/health")
