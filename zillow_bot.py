import time
import datetime
import os
import gspread
from fastapi import FastAPI
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from oauth2client.service_account import ServiceAccountCredentials

app = FastAPI()

# 1️⃣ Google Sheets Setup
def get_contractor_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)

    sheet = client.open("Contractor_Status")  # Update with actual sheet name
    main_sheet = sheet.worksheet("Main")  # Assuming the main sheet is named "Main"
    log_sheet = sheet.worksheet("Log")  # Log sheet for status updates
    
    data = main_sheet.get_all_records()
    return sheet, main_sheet, log_sheet, data

# 2️⃣ Setup Selenium WebDriver
def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run without UI
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(options=options)
    return driver

# 3️⃣ Login to Zillow CRM
def login_zillow(driver, email, password):
    driver.get("https://premieragent.zillow.com/crm/")
    time.sleep(3)

    email_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "reg-login-email")))
    password_input = driver.find_element(By.ID, "inputs-password")

    email_input.send_keys(email)
    password_input.send_keys(password)
    email_input.send_keys(Keys.RETURN)

    time.sleep(5)
    print("✅ Successfully Logged into Zillow CRM!")

# 4️⃣ Navigate to Team Management Page
def navigate_to_team_management(driver):
    driver.get("https://premieragent.zillow.com/leads/routing/agent-capacity")
    time.sleep(5)
    print("✅ Navigated to Team Management Page")

# 5️⃣ Update Contractor Status
def update_contractor_status(driver, data):
    wait = WebDriverWait(driver, 10)

    activated_contractors = []  
    paused_contractors = []  
    previous_statuses = {}  
    updated_statuses = {}  

    for row in data:
        name = row["Contractor Name"]
        pause_status = row["Pause Status"]

        time.sleep(5)  

        rows = driver.find_elements(By.XPATH, "//tr[contains(@class, 'StyledTableRow')]")
        
        for table_row in rows:
            try:
                time.sleep(5)  
                name_element = driver.find_element(By.XPATH, f"//div[contains(text(),'{name}')]")
                contractor_name = name_element.text.strip()
                
                if contractor_name == name and name != "Engel and Völkers New Orleans":
                    print(f"🔍 Found: {contractor_name}")

                    expand_button = table_row.find_element(By.XPATH, f"//button[@aria-label='Expand row for {contractor_name}']")
                    expand_button.click()
                    time.sleep(5)  

                    checkbox = wait.until(EC.presence_of_element_located((By.XPATH, "//td[contains(@class, 'StyledTableCell') and @colspan='7']//input[@type='checkbox' and contains(@class, 'StyledCheckbox')]")))

                    driver.execute_script("arguments[0].scrollIntoView();", checkbox)
                    current_status = "Paused" if checkbox.is_selected() else "Active"
                    
                    previous_statuses[contractor_name] = current_status

                    if pause_status == "Paused" and current_status == "Active":
                        # checkbox.click()
                        paused_contractors.append(contractor_name)
                        updated_statuses[contractor_name] = "Paused"
                        print(f"✅ Paused {contractor_name}")
                    elif pause_status == "Active" and current_status == "Paused":
                        # checkbox.click()
                        activated_contractors.append(contractor_name)
                        updated_statuses[contractor_name] = "Active"
                        print(f"✅ Activated {contractor_name}")
                    else:
                        updated_statuses[contractor_name] = current_status

                    break  
            
            except Exception as e:
                print(f"⚠️ Error updating {name}: {e}")

    return activated_contractors, paused_contractors, previous_statuses, updated_statuses  

# 6️⃣ Log Status Change to Google Sheet
def log_status_change(log_sheet, previous_statuses, updated_statuses):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_week = datetime.datetime.today().isocalendar()[1]

    for name in previous_statuses:
        log_sheet.append_row([
            current_time, 
            current_week, 
            name, 
            previous_statuses[name], 
            updated_statuses[name]
        ])
    
    print("✅ Status changes logged in Google Sheets!")

# 7️⃣ API Endpoint to Trigger the Bot
@app.get("/run")
def run_bot():
    EMAIL = os.getenv("EMAIL")
    PASSWORD = os.getenv("PASSWORD")

    if not EMAIL or not PASSWORD:
        return {"error": "Missing environment variables: EMAIL or PASSWORD"}

    sheet, main_sheet, log_sheet, contractor_data = get_contractor_data()
    driver = setup_driver()

    try:
        login_zillow(driver, EMAIL, PASSWORD)
        navigate_to_team_management(driver)

        activated_contractors, paused_contractors, previous_statuses, updated_statuses = update_contractor_status(driver, contractor_data)

        log_status_change(log_sheet, previous_statuses, updated_statuses)

        return {
            "message": "Bot executed successfully",
            "activated": activated_contractors,
            "paused": paused_contractors
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        driver.quit()
