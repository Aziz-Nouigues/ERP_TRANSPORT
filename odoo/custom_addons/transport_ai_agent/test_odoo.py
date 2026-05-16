import xmlrpc.client
from dotenv import load_dotenv
import os

load_dotenv()

# Debug : vérifie ce qui est chargé
print("URL  :", os.getenv("ODOO_URL"))
print("DB   :", os.getenv("ODOO_DB"))
print("USER :", os.getenv("ODOO_USER"))

url  = os.getenv("ODOO_URL")
db   = os.getenv("ODOO_DB")
user = os.getenv("ODOO_USER")
pwd  = os.getenv("ODOO_PASSWORD")

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
uid    = common.authenticate(db, user, pwd, {})

models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
nb = models.execute_kw(db, uid, pwd,
    'transport.exploitation.tournee', 'search_count', [[]])

print(f"Odoo OK — uid={uid} — tournées : {nb}")