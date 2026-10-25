# DevOps Lab Mid: Notes App on AWS (Docker + Compose + ALB + ASG + Selenium)

**Notes Manager** is a multi-user notes app built with Flask, PostgreSQL and Redis, served
through an Nginx reverse proxy. It is containerised with Docker, run with Docker Compose
(4 containers), deployed on EC2 instances behind an Application Load Balancer and Auto
Scaling Group, and tested end to end with Selenium (14 tests).

**App features**
- Register / log in / log out, passwords hashed (never stored as plain text)
- Sessions stored server-side in Redis; 5 wrong passwords lock the username for 5 minutes
- Each user sees only their own notes (others' notes return 404)
- Notes have title, content, category (Work/Study/Personal/Other), priority (High/Medium/Low), pin
- Search, category filter, 4 sort orders, pagination (6 per page), stats dashboard
- CSRF tokens on every form, input validation, parameterised SQL, safe redirects, escaped output
- JSON API: `GET /api/notes` (optionally `?category=Work`)

```
Inside each EC2:

  ALB ──► :80 nginx ──(frontend network)──► web:5000 (Flask/Gunicorn)
                                               │
                              (backend network)├──► db:5432    (PostgreSQL) ──► volume pgdata
                                               └──► redis:6379 (Redis)      ──► volume redisdata
```
Only Nginx is published on a host port. Flask, Postgres and Redis are reachable only
inside Docker networks, and Nginx cannot reach the databases at all.

```
devops-lab/
├── app/
│   ├── app.py              # creates the app: CSRF protection, /health, error pages
│   ├── config.py           # settings from environment variables
│   ├── db.py               # PostgreSQL connection pool + safe cursor helper
│   ├── cache.py            # Redis clients
│   ├── auth.py             # register / login (lockout) / logout, login_required
│   ├── notes.py            # dashboard, search/filter/sort/pages, CRUD, pin, JSON API
│   ├── schema.sql          # users + notes tables, constraints, index
│   ├── templates/          # base, login, register, index, edit, error pages
│   ├── static/style.css
│   ├── requirements.txt
│   ├── Dockerfile          # custom image (Task 3)
│   └── .dockerignore
├── nginx/nginx.conf        # reverse proxy config (bind-mounted into nginx container)
├── docker-compose.yml      # nginx + web + db + redis, 2 named volumes, 2 networks (Tasks 4, 5)
├── .env.example            # DB credentials + SECRET_KEY template
├── selenium/test_app.py    # Selenium test (Task 6)
└── scripts/
    ├── linux_admin.sh      # Linux commands demo (Task 2)
    ├── volume_demo.sh      # persistence demo (Task 4)
    └── ec2_user_data.sh    # Launch Template user data (Task 1)
```

---

## STEP 0: Push the project to GitHub

```bash
cd devops-lab
git init && git add . && git commit -m "DevOps lab mid"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```
Make the repo **public** (or the EC2 user-data can't clone it). Put the URL into
`scripts/ec2_user_data.sh` → `REPO_URL`.

---

## STEP 1 (Task 3 + 5): Run locally first

Needs Docker Desktop (Windows/Mac) or Docker on Linux.

```bash
cp .env.example .env                 # create credentials file (then edit the values)
docker build -t notes-web:3.0 ./app  # Task 3: build custom image
docker images                        # show the image
docker compose up -d --build         # Task 5: start nginx + web + db + redis
docker compose ps                    # 4 containers; web, db, redis "healthy"
docker compose logs web
docker network ls                    # shows the frontend and backend networks
```
Open http://localhost. You land on the login page. Create an account, then add notes in
different categories and priorities, and try search, filters, pin, edit and delete.

> **Ran an older version of this project before?** The database tables changed. Run
> `docker compose down -v` once (this deletes the old volumes), then `up` again.

Show multi-container communication for the viva:
```bash
docker exec notes-web python -c "import socket; print(socket.gethostbyname('db'))"    # Docker DNS
docker exec notes-db psql -U notesuser -d notesdb -c "SELECT id, username, LEFT(password_hash, 30) FROM users;"  # hashed passwords
docker exec notes-db psql -U notesuser -d notesdb -c "SELECT id, user_id, title, category, priority, pinned FROM notes;"
docker exec notes-redis redis-cli --scan --pattern 'notes:*'                           # sessions, counters
docker exec notes-redis redis-cli TTL notes:login_fail:<username>                      # lockout timer
docker exec notes-nginx wget -qO- http://web:5000/health                               # nginx -> web
```

Task 3 also says "run a container". For a quick single-container demo:
```bash
docker run -d --name single-test -p 8080:5000 -e DB_HOST=host.docker.internal notes-web:3.0
docker ps
docker rm -f single-test
```
(Without a DB the page errors, which is fine. The point is showing `docker run`. The Compose run is the real app.)

---

## STEP 2 (Task 2): Launch one EC2 and do Linux admin

1. **EC2 → Launch instance**
   - AMI: **Amazon Linux 2023**, type **t2.micro / t3.micro** (free tier)
   - Key pair: create one (`.pem`)
   - Security group `web-sg`: inbound **SSH 22** (My IP), **HTTP 80** (Anywhere for now)
2. Connect: `ssh -i key.pem ec2-user@<public-ip>` (or EC2 Instance Connect in the browser)
3. Run the commands in `scripts/linux_admin.sh` **one by one** and screenshot them.

Key permission facts for the viva:

| Number | Symbolic | Meaning |
|---|---|---|
| 7 | rwx | read + write + execute (4+2+1) |
| 6 | rw- | read + write |
| 5 | r-x | read + execute |
| 4 | r-- | read only |
| `chmod 755 dir` | rwxr-xr-x | owner full, group/others read+enter |
| `chmod 600 file` | rw------- | only owner (use for keys/secrets) |

`chmod 400 key.pem` is required before SSH accepts your key. That's a good viva example.

---

## STEP 3: Install Docker on that EC2 and run the app

```bash
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user && newgrp docker
docker --version

# Compose plugin
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m) \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version

git clone https://github.com/<you>/<repo>.git app && cd app
cp .env.example .env
docker compose up -d --build
docker ps
```
Open `http://<EC2-public-ip>`. App works on one instance.

---

## STEP 4 (Task 4): Volume persistence demo

First register a user and add a few notes in the browser. Then, on the EC2 (inside `app/`):
```bash
bash scripts/volume_demo.sh
```
It shows users and their note counts, the visit counter and the number of active sessions,
runs `docker compose down` (all containers deleted), runs `up` again, and shows the same
data. Refresh the browser afterwards: you are **still logged in**, because your session
survived in Redis. Postgres keeps its data in `pgdata`; Redis writes to disk
(`--appendonly yes`) in `redisdata`.

**Warning:** `docker compose down -v` deletes the volume too. Never use `-v` in the demo.
(If you change `POSTGRES_USER`/`POSTGRES_DB` in `.env`, edit them in the script too.)

---

## STEP 5 (Task 1): Launch Template → Target Group → ALB → Auto Scaling Group

Do it in this order in the AWS console (all in the same region):

### 5a. Security groups
- `alb-sg`: inbound **HTTP 80 from 0.0.0.0/0**
- `web-sg`: inbound **HTTP 80 from `alb-sg`** (source = the security group), SSH 22 from My IP

### 5b. Launch Template (EC2 → Launch Templates → Create)
- Name `notes-lt`, AMI Amazon Linux 2023, t2/t3.micro, your key pair, SG `web-sg`
- **Advanced details → User data**: paste `scripts/ec2_user_data.sh` (with your repo URL)

### 5c. Target Group (EC2 → Target Groups → Create)
- Type **Instances**, protocol HTTP, port **80**, your default VPC
- Health check path: **`/health`**
- Don't register targets manually; the ASG will do it.
- After creating it: **Target group → Attributes → Edit → turn on Stickiness**, type
  **Load balancer generated cookie**, duration **1 hour**.

> **Why stickiness is required:** each EC2 has its own Redis (sessions) and its own database
> (users and notes). Without stickiness the ALB could send your next click to the other
> instance, which has never heard of your session or your account, so you'd be logged out.
> Stickiness keeps each browser on one instance. The real-world fix is a shared database
> (Amazon RDS) and shared cache (ElastiCache) so any instance can serve any user.

### 5d. Application Load Balancer (EC2 → Load Balancers → Create → Application)
- Name `notes-alb`, **Internet-facing**, select **at least 2 Availability Zones / subnets**
- SG `alb-sg`
- Listener HTTP:80 → forward to your target group

### 5e. Auto Scaling Group (EC2 → Auto Scaling Groups → Create)
- Launch template `notes-lt`, same VPC, same 2+ subnets
- **Attach to existing load balancer** → choose your target group
- Turn on **ELB health checks**, grace period 300 s
- Capacity: **Desired 2, Min 2, Max 4**
- Scaling policy: **Target tracking, Average CPU 50%**

Wait ~3–5 minutes for user data to finish, then check **Target Group → Targets** shows 2 **healthy**.
Open the ALB **DNS name** (`notes-alb-xxxx.<region>.elb.amazonaws.com`).

### 5f. Demonstrate (screenshots!)
1. **Load balancing**: because of stickiness, one browser stays on one instance. To show both
   instances, run this a few times (curl sends no cookie, so the ALB spreads requests):
   ```bash
   for i in 1 2 3 4 5 6; do curl -s http://<ALB-DNS-name>/health; echo; done
   ```
   `served_by` alternates between the two instances. You can also open the app in a normal
   window and an incognito window: "Served by container" usually differs.
2. **Auto scaling / self-healing**: terminate one instance → ASG **Activity** tab shows a replacement launched → target back to healthy.
3. (Optional) Edit desired capacity to 3 and watch a new instance join.

---

## STEP 6 (Task 6): Selenium test

Run on your laptop (needs Chrome + Python):
```bash
pip install selenium
python selenium/test_app.py http://<ALB-DNS-name>
# or headless:
python selenium/test_app.py http://<ALB-DNS-name> --headless
```
Expected output (each run registers a fresh user, so you can run it many times):
```
[PASS] Test  1: protected page redirected to login, title = Log in | Notes Manager
[PASS] Test  2: registered and logged in -> 'Hi, tester_1792910922'
[PASS] Test  3: heading element found -> My Notes
[PASS] Test  4: created 2 notes, total stat = 2
[PASS] Test  5: search 'checklist' shows only the Work note
[PASS] Test  6: category filter 'Study' shows only the Study note
[PASS] Test  7: pinned note moved to the top, pinned stat = 1
[PASS] Test  8: note edited -> 'Deploy checklist ... (done)', priority Medium
[PASS] Test  9: note deleted, total stat = 1
[PASS] Test 10: visit counter changed: 'Page visits: 10' -> 'Page visits: 11'
[PASS] Test 11: JSON API /api/notes returns 1 note for this user
[PASS] Test 12: logged out; notes page redirects to login again
[PASS] Test 13: wrong password rejected -> 'Invalid username or password. 4 attempt(s) left.'
[PASS] Test 14: logged back in, saved note still there
All 14 tests passed. Screenshot saved: selenium_result.png
```
Selenium techniques used: `By.ID`, `By.CLASS_NAME`, `By.CSS_SELECTOR`, `By.XPATH`
(finding a note card by its title), `Select` for dropdowns, explicit waits
(`url_contains`, `text_to_be_present_in_element`, `alert_is_present` for the delete
confirmation popup), and a screenshot on pass or fail. Against the ALB, stickiness must be on.

---

## Evidence checklist (screenshot each)

- [ ] `ls -l` / `chmod` / `mkdir` output on EC2
- [ ] `docker --version`, `docker compose version`
- [ ] `docker build` output and `docker images`
- [ ] `docker compose ps` (4 containers, healthy)
- [ ] `docker network ls` and the `docker exec` communication commands
- [ ] `docker volume ls` and before/after persistence output (notes + counter)
- [ ] Target Group with 2 healthy targets and stickiness on
- [ ] ALB DNS URL working in browser; `curl /health` loop showing both instances
- [ ] ASG Activity tab showing replacement instance
- [ ] Selenium terminal output + `selenium_result.png`

**After the viva:** delete ASG → ALB → Target Group → Launch Template to avoid charges.

---

## Viva prep (Section B, 15 marks)

### AWS EC2, ALB, ASG (3)
- **EC2**: virtual server in AWS. **AMI** = OS image, **instance type** = CPU/RAM size, **security group** = stateful virtual firewall.
- **ALB**: Layer 7 (HTTP) load balancer. Gives one DNS name, spreads traffic across healthy targets, uses health checks (`/health`). NLB is Layer 4 (TCP).
- **Target group**: the set of instances the ALB forwards to, plus health-check settings.
- **ASG**: keeps min/desired/max instances, replaces unhealthy ones, scales on policies (CPU target tracking). Uses a **Launch Template**.
- **Why 2 AZs?** High availability: if one data centre fails, the other still serves.
- **User data**: a script that runs on first boot to configure the instance automatically.
- **Scale out vs scale up**: more instances (horizontal) vs bigger instance (vertical).

### Linux (2)
- `ls -la`, `pwd`, `cd`, `mkdir -p`, `touch`, `cp`, `mv`, `rm`, `cat`, `grep`, `ps`, `df -h`, `free -h`, `systemctl`
- Permissions: r=4 w=2 x=1, for owner/group/others. `chmod`, `chown user:group`, `sudo`.
- `x` on a directory means you can `cd` into it.

### Docker images/Dockerfile/containers (3)
- **Image** = read-only template (layers). **Container** = running instance of an image.
- `FROM`, `WORKDIR`, `COPY`, `RUN` (build time), `CMD` (run time), `EXPOSE`, `ENV`, `USER`, `HEALTHCHECK`.
- `RUN` executes while building; `CMD` is the default command when the container starts; `ENTRYPOINT` is harder to override.
- Copying `requirements.txt` before the code uses **layer caching** so rebuilds are fast.
- `slim` base image + non-root user + `.dockerignore` = smaller and more secure.
- Commands: `docker build -t`, `run -d -p`, `ps`, `logs`, `exec -it`, `stop`, `rm`, `images`, `rmi`.

### Volumes (2)
- Container filesystem is deleted with the container; **volumes** live outside it.
- **Named volume** (managed by Docker, `/var/lib/docker/volumes/...`) vs **bind mount** (a host folder you choose).
- `docker compose down` keeps volumes; `down -v` deletes them.

### Compose and multi-container communication (3)
- Compose defines multi-container apps in one YAML file: `services`, `networks`, `volumes`.
- Containers on the same Compose network reach each other by **service name** (`DB_HOST=db`, `REDIS_HOST=redis`, `server web:5000` in Nginx) via Docker's built-in DNS.
- **Two networks**: `frontend` (nginx ↔ web) and `backend` (web ↔ db, redis). Web is on both; Nginx can't reach the databases. This is network segmentation.
- `ports: "80:80"` on nginx publishes it to the host. `expose: 5000` on web only documents the port for other containers; it is **not** published. DB and Redis have no ports at all.
- **Reverse proxy**: Nginx receives every request and forwards it to Gunicorn. Benefits: one public entry point, security headers, timeouts, could serve static files and HTTPS, and Gunicorn is never exposed directly.
- **Redis**: an in-memory key-value store. Here it holds **sessions** (Flask-Session), **failed-login counters** that expire by themselves (`INCR` + `EXPIRE`), and a **visit counter**. Because login needs Redis, `/health` returns 500 if Redis or Postgres is down, so the ALB stops sending traffic to that instance.
- `depends_on` + `condition: service_healthy` = startup order nginx ← web ← db + redis, each waiting until the one before is healthy.
- **Bind mount vs named volume** in one file: `./nginx/nginx.conf:...:ro` is a bind mount (a host file, read-only); `pgdata` and `redisdata` are named volumes.
- `restart: unless-stopped` = auto-restart on crash/reboot.
- Gunicorn runs several workers that all start at once, so table creation uses a Postgres **advisory lock** to stop two workers creating the table at the same time.

### The application itself (likely questions)
- **Structure**: Flask **blueprints** split the app: `auth` (accounts) and `notes` (features). `app.py` wires them together; settings come from environment variables (12-factor style), so the same image runs anywhere.
- **Passwords**: `generate_password_hash` stores a salted hash (scrypt/pbkdf2), never the password. `check_password_hash` compares at login.
- **Sessions**: the browser cookie holds only a random session ID; the data (`user_id`, CSRF token) lives in Redis. `session.clear()` on login prevents **session fixation**. The cookie is `HttpOnly` (JavaScript can't read it) and `SameSite=Lax`.
- **Login lockout**: key `notes:login_fail:<username>` counts failures with `INCR`; `EXPIRE 300` makes Redis delete it after 5 minutes. At 5 failures login returns **429 Too Many Requests**. The error message doesn't say whether the username exists.
- **CSRF**: every form has a hidden random token that must match the one in the session, so another website can't submit forms as you. Missing or wrong token → **400**.
- **SQL injection**: all user input goes in as `%s` parameters, so `' OR 1=1 --` in search is treated as text and finds nothing.
- **Authorisation**: every note query includes `AND user_id = <current user>`; another user's note gives **404**, not 403, so its existence isn't revealed.
- **XSS**: Jinja escapes output, so a note titled `<script>` is shown as text, not run.
- **Database design**: `users` 1-to-many `notes` via a **foreign key** with `ON DELETE CASCADE`; `CHECK` constraints only allow valid categories/priorities; an **index** on `notes.user_id` because every query filters by it; `UNIQUE` username.
- **Pagination**: `LIMIT 6 OFFSET (page-1)*6`, plus a `COUNT(*)` for the page total; out-of-range pages are clamped.
- **Stats**: one query with `COUNT(*) FILTER (WHERE ...)` and one `GROUP BY category`.
- **Connection pool**: `ThreadedConnectionPool` reuses database connections instead of opening a new one per request; broken connections are discarded.
- **Advisory lock**: Gunicorn starts several workers at once and each runs `schema.sql`; `pg_advisory_xact_lock` makes them take turns so table creation can't collide.
- **HTTP methods**: reads are `GET` (filters live in the URL, so they can be bookmarked); anything that changes data is `POST` and redirects afterwards (Post/Redirect/Get), so refreshing doesn't resubmit.

### Selenium (2)
- Automates a real browser for UI/end-to-end testing. **WebDriver** = API controlling the browser via a driver (ChromeDriver).
- Locators: `By.ID`, `By.NAME`, `By.CLASS_NAME`, `By.CSS_SELECTOR`, `By.XPATH`.
- **Explicit wait** (`WebDriverWait` + `expected_conditions`) waits for a condition; better than `time.sleep`.
- **Headless** mode = no visible window (used in CI pipelines).
- Assertions decide pass/fail.
