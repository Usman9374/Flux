Read my entire codebase and figure out what ive done, remember that every phase in my @readmealways.md file has been completed. also already connected with the backend postgresql://postgres:Vspecgtr2005.@db.ofhanqmsyjghfcpmbfev.supabase.co:5432/postgres you can see it in my code and on render i have the env variables 

CORS_ORIGINS: http://localhost:5173,http://127.0.0.1:5173

DATABASE_URL:  postgresql://postgres.ofhanqmsyjghfcpmbfev:Vspecgtr2005.@aws-1-ap-south-1.pooler.supabase.com:5432/postgres
ENVIRONMENT: 
production

PLAYWRIGHT_BROWSERS_PATH: /opt/render/project/src/.playwright
PYTHON_VERSION: 3.12.7

and in my settings of render i have these:
General
Name
A unique name for your Web Service.
Flux

Edit
Region
Your services in the same region can communicate over a private network.
Singapore (Southeast Asia)
Instance Type
Free
0.1 CPU
512 MB
Update
See remaining free usage, or learn about free service limits.
Build
Source
The build source for your Web Service
https://github.com/Usman9374/Flux

Edit
Branch
The Git branch to build and deploy.
Branch
main

Edit
Root DirectoryOptional
If set, Render runs commands from this directory instead of the repository root. Additionally, code changes outside of this directory do not trigger an auto-deploy. Most commonly used with a monorepo.
backend

Edit
Build Command
Render runs this command to build your app before each deploy.
backend/ $
bash build.sh

Edit
Git Credentials
User providing the credentials to pull the repository.
usmanthekilla99@gmail.com (you)
Use My Credentials
Build Filters
Include or ignore specific paths in your repo when determining whether to trigger an auto-deploy. Paths are relative to your repo's root directory. Learn more.

Edit
Included Paths
Changes that match these paths will trigger a new build.


Add Included Path
Ignored Paths
Changes that match these paths will not trigger a new build.


Add Ignored Path
Deploy
Pre-Deploy CommandOptional
Render runs this command before the start command. Useful for database migrations and static asset uploads.
backend/ $

Edit
Start Command
Render runs this command to start your app with each deploy.
backend/ $
uvicorn app.main:app --host 0.0.0.0 --port $PORT

https://api.render.com/deploy/srv-d7rnennlk1mc73d9ruo0?key=01M4mf9lkpM

Edit
Auto-Deploy
By default, Render automatically deploys your service whenever you update its code or configuration. Disable to handle deploys manually. Learn more.
autoDeployTrigger

On Commit

Edit
Deploy Hook
Your private URL to trigger a deploy for this server. Remember to keep this a secret.
••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••



Regenerate hook
Custom Domains
You can point custom domains you own to this service.


Add Custom Domain
Render Subdomain
If enabled, your service remains reachable at its onrender.com subdomain in addition to all custom domains. Disable to serve exclusively from custom domains.


enabled
Your service is reachable at https://flux-h0va.onrender.com.
PR Previews
Pull Request Previews
Spin up temporary instances to test pull requests opened against the main branch of Usman9374/Flux. Choose Automatic to preview all PRs, or Manual for only PRs with [render preview] in their title. Pull Request Previews create a new instance for just this service. Use Preview Environments to clone a group of services for every PR.
prPreviewsEnabled

Off

Edit
Edge Caching
Serve static content at the edge to improve performance and reduce service load. Learn more.
Paid
Edge Caching is only available for paid instances.
Upgrade
Notifications
Service Notifications
Set notifications to receive for your service. This setting will override your workspace's default settings.
notificationsToSend

Use workspace default (Only failure notifications)

Edit
Preview Environment Notifications
Configure notifications for preview environments and service previews.
previewNotificationsEnabled

Use account default (Disabled)

Edit
Health Checks
Health Check Path
Provide an HTTP endpoint path that Render messages periodically to monitor your service. Learn More.

Edit
Maintenance Mode




the website is live on vercel and completely fine https://flux-leads.vercel.app 

