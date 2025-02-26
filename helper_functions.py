import os
import csv
import gspread
import json
import logging
import sys
from google.oauth2.service_account import Credentials
import configs

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def setup_google_sheet(credentials_file, spreadsheet_id, sheet_name):
    """
    Sets up and returns a Google Sheet worksheet.
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
    return sheet

def get_input_sheet():
    """
    Gets records from the input Google Sheet.
    """
    google_sheet_info = configs.event.get("google_sheet")
    if google_sheet_info:
        logging.info("Setting up Google Sheets")
        # Setup Input Sheet
        input_sheet = setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            google_sheet_info["input_sheet_name"]
        )

        # Assume the first row is headers
        records = input_sheet.get_all_records()
        return records
    else:
        logging.error("No Google Sheet information provided in the event data.")
        return []

def get_question_inputs(records):
    """
    Extracts question data from records.
    Returns a list of tuples with (question, question_type, unit, question_id)
    """
    # Initialize lists
    questions = []
    question_types = []
    units = []
    question_ids = []
    
    for idx, record in enumerate(records, start=1):
        try:
            question_type = record["Question Type"]
            unit = record["Units"]
            question = record["Formatted FRQ"]
            question_id = record["ID"]

            questions.append(question)
            question_types.append(question_type)
            units.append(unit)
            question_ids.append(question_id)

        except KeyError as key_err:
            logging.error(f"Missing expected key in record {idx}: {str(key_err)}\nRecord Data: {record}")
            continue
    
    # Return a list of tuples with all the question data
    return list(zip(questions, question_types, units, question_ids))

def setup_output_files():
    """
    Sets up output files for FRQ responses and grading.
    Returns a tuple of (frq_output_path, output_files)
    """
    # Setup FRQ output file
    frq_headers = [
        "Question ID",
        "Question",
        "Question Type",
        "Unit",
        "Responses",
        "Facts Referenced",
        "Combined Response with Facts",
        "Reasoning",
        "Raw JSON"
    ]
    
    output_folder = "outputs"
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(f"{output_folder}/grading", exist_ok=True)
    
    # Create output file path for FRQ responses
    frq_output_file = f"{configs.event.get('output_file')}"
    frq_output_path = os.path.join(output_folder, frq_output_file)
    
    # Create file and write headers if not exists
    if not os.path.exists(frq_output_path):
        try:
            with open(frq_output_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=frq_headers)
                writer.writeheader()
            logging.info(f"Created output CSV file with headers: {frq_output_path}")
        except Exception as e:
            logging.error(f"Failed to create output CSV file: {str(e)}")
            sys.exit(1)
    
    # Create output files for grading
    saq_headers = [
        'Question ID', 'Question', 'Question Type', 'Unit', 'Response',
        'Part A Score', 'Part A Evaluation',
        'Part B Score', 'Part B Evaluation',
        'Part C Score', 'Part C Evaluation',
        'Total Score', 'Raw JSON'
    ]
    
    leq_headers = [
        'Question ID', 'Question', 'Question Type', 'Unit', 'Response',
        'Thesis Construction Score', 'Thesis Response Evaluation',
        'Contextualization Score', 'Contextualization Response Evaluation',
        'LEQ Outside Evidence Score', 'LEQ Outside Evidence Response Evaluation',
        'Historical Reasoning Score', 'Historical Reasoning Response Evaluation',
        'LEQ Complexity Score', 'LEQ Complexity Response Evaluation',
        'Total Score', 'Raw JSON'
    ]
    
    dbq_headers = [
        'Question ID', 'Question', 'Question Type', 'Unit', 'Response',
        'Thesis Construction Score', 'Thesis Response Evaluation',
        'Contextualization Score', 'Contextualization Response Evaluation',
        'Document Use Score', 'Document Use Response Evaluation',
        'DBQ Outside Evidence Score', 'DBQ Outside Evidence Response Evaluation',
        'Document Analysis Score', 'Document Analysis Response Evaluation',
        'Historical Reasoning Score', 'Historical Reasoning Response Evaluation',
        'DBQ Complexity Score', 'DBQ Complexity Response Evaluation',
        'Total Score', 'Raw JSON'
    ]
    
    # Create output files with appropriate headers
    output_files = {
        'SAQs': ('outputs/grading/saq_graded.csv', saq_headers),
        'LEQs': ('outputs/grading/leq_graded.csv', leq_headers),
        'DBQs': ('outputs/grading/dbq_graded.csv', dbq_headers)  
    }
    
    for file_path, headers in output_files.values():
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
    
    return frq_output_path, output_files

def write_to_frq_sheet(frq_output_path):
    """
    Writes FRQ responses from CSV to Google Sheet.
    """
    google_sheet_info = configs.event.get("google_sheet")
    if not google_sheet_info:
        logging.error("No Google Sheet information for writing FRQ results")
        return
    
    try:
        output_sheet = setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            google_sheet_info["frq_output_sheet_name"]
        )
        
        # Clear existing data (except headers)
        output_sheet.clear()
        output_sheet.update("A1", [["Question ID", "Question", "Question Type", "Unit", 
                             "Responses", "Facts Referenced", "Combined Response with Facts",
                             "Reasoning", "Raw JSON"]])
        
        # Read from CSV file
        with open(frq_output_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
        
        # Skip header row (already added)
        data_to_append = []
        for row in rows:
            data_to_append.append([
                row['Question ID'],
                row['Question'],
                row['Question Type'],
                row['Unit'],
                row['Responses'],
                row['Facts Referenced'],
                row['Combined Response with Facts'],
                row['Reasoning'],
                row['Raw JSON']
            ])
        
        # Append all rows at once (faster than one by one)
        if data_to_append:
            output_sheet.update("A2", data_to_append)
            
        logging.info(f"Successfully wrote {len(data_to_append)} FRQ responses to Google Sheet")
    except Exception as e:
        logging.error(f"Failed to write to Google Sheet: {str(e)}")

def write_to_grading_sheet(grading_outputs):
    """
    Writes grading results from CSV files to Google Sheets (one sheet per question type).
    """
    google_sheet_info = configs.event.get("google_sheet")
    if not google_sheet_info:
        logging.error("No Google Sheet information for writing grading results")
        return
    
    # Sheet names for each question type should be provided in the config
    sheet_mapping = {
        'SAQs': google_sheet_info.get("saq_grading_sheet_name", "SAQ Grading"),
        'LEQs': google_sheet_info.get("leq_grading_sheet_name", "LEQ Grading"),
        'DBQs': google_sheet_info.get("dbq_grading_sheet_name", "DBQ Grading")
    }
    
    # Process each question type
    for question_type, (file_path, headers) in grading_outputs.items():
        try:
            # Get the appropriate sheet for this question type
            output_sheet = setup_google_sheet(
                google_sheet_info["credentials_file"],
                google_sheet_info["spreadsheet_id"],
                sheet_mapping[question_type]
            )
            
            # Clear existing data (except headers)
            output_sheet.clear()
            
            # Add headers
            output_sheet.update("A1", [headers])
            
            # Read data from CSV
            data_to_append = []
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                data_to_append = list(reader)
            
            # Append data if available
            if data_to_append:
                output_sheet.update("A2", data_to_append)
                
            logging.info(f"Successfully wrote {len(data_to_append)} {question_type} grading results to Google Sheet")
        except Exception as e:
            logging.error(f"Failed to write {question_type} to Google Sheet: {str(e)}")

# Read facts from the corresponding unit's CSV file
def get_facts_for_unit(unit_number):
    facts_dir = "KS_facts"
    # Find the CSV file that matches the unit number
    for filename in os.listdir(facts_dir):
        if filename.startswith(f"unit{unit_number}") and filename.endswith(".csv"):
            facts_path = os.path.join(facts_dir, filename)
            with open(facts_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)  # Skip header row
                facts = [row[2] for row in reader if row and len(row) > 2]  # Column C (index 2)
                return "\n".join(facts)
    raise FileNotFoundError(f"No facts file found for unit {unit_number}")

def format_response_data(function_args, question_type):
    """
    Format the API response data based on question type.
    Returns tuple of (responses, facts_referenced, combined_response)
    """
    if question_type == "SAQs":
        parts = ['a', 'b', 'c']
        
        # Format each part's response and facts
        formatted_parts = []
        for part in parts:
            response = function_args["answers"][part]["response"]
            facts = function_args["answers"][part]["facts_referenced"]
            formatted_parts.append({
                'part': part.lower(),
                'response': response,
                'facts': facts
            })
        
        # Create the three column formats
        responses = "\n\n".join([
            f"{part['part']}. {part['response']}"
            for part in formatted_parts
        ])
        
        facts_referenced = "\n\n".join([
            f"{part['part']} Facts:\n{', '.join(part['facts'])}"
            for part in formatted_parts
        ])
        
        combined = "\n\n".join([
            f"{part['part']}. {part['response']}\nFacts Referenced: {', '.join(part['facts'])}"
            for part in formatted_parts
        ])
        
        return responses, facts_referenced, combined
    
    elif question_type in ["LEQs", "DBQs"]:
        # For LEQs and DBQs, we have a single response with facts_used
        response = function_args["response"]
        facts = function_args["facts_used"]
        
        facts_referenced = ", ".join(facts)
        combined = f"{response}\nFacts Referenced: {facts_referenced}"
        
        return response, facts_referenced, combined
    
    # Return empty strings if question type not recognized
    return "", "", ""

def write_saq_grade(file_path, question_id, question, question_type, unit, responses, grading_json):
    # Initialize scores and evaluations
    part_scores = {'a': 0, 'b': 0, 'c': 0}
    part_evals = {'a': '', 'b': '', 'c': ''}
    
    # Extract scores and evaluations from grading JSON
    for part in grading_json['subParts']:
        part_id = part['id']
        part_scores[part_id] = part['score']
        part_evals[part_id] = part['response_evaluation']
    
    total_score = sum(part_scores.values())
    
    with open(file_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            question_id,
            question,
            question_type,
            unit,
            responses,
            part_scores['a'],
            part_evals['a'],
            part_scores['b'],
            part_evals['b'],
            part_scores['c'],
            part_evals['c'],
            total_score,
            json.dumps(grading_json)
        ])

def write_leq_grade(file_path, question_id, question, question_type, unit, responses, grading_json):
    # Initialize scores dictionary
    skill_scores = {
        'Thesis Construction': 0,
        'Contextualization': 0,
        'LEQ Outside Evidence': 0,
        'Historical Reasoning': 0,
        'LEQ Complexity': 0
    }
    skill_evals = {
        'Thesis Construction': '',
        'Contextualization': '',
        'LEQ Outside Evidence': '',
        'Historical Reasoning': '',
        'LEQ Complexity': ''
    }

    # Extract scores from grading JSON
    for part in grading_json['subParts']:
        skill = part['name']
        skill_scores[skill] = part['score']
        skill_evals[skill] = part['response_evaluation']
    
    total_score = sum(skill_scores.values())
    
    with open(file_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            question_id,
            question,
            question_type,
            unit,
            responses,
            skill_scores['Thesis Construction'],
            skill_evals['Thesis Construction'],
            skill_scores['Contextualization'],
            skill_evals['Contextualization'],
            skill_scores['LEQ Outside Evidence'],
            skill_evals['LEQ Outside Evidence'],
            skill_scores['Historical Reasoning'],
            skill_evals['Historical Reasoning'],
            skill_scores['LEQ Complexity'],
            skill_evals['LEQ Complexity'],
            total_score,
            json.dumps(grading_json)
        ])

def write_dbq_grade(file_path, question_id, question, question_type, unit, responses, grading_json):
    # Initialize scores dictionary
    skill_scores = {
        'Thesis Construction': 0,
        'Contextualization': 0,
        'Document Use': 0,
        'DBQ Outside Evidence': 0,
        'Document Analysis': 0,
        'Historical Reasoning': 0,
        'DBQ Complexity': 0
    }
    skill_evals = {
        'Thesis Construction': '',
        'Contextualization': '',
        'Document Use': '',
        'DBQ Outside Evidence': '',
        'Document Analysis': '',
        'Historical Reasoning': '',
        'DBQ Complexity': ''
    }

    # Extract scores from grading JSON
    for part in grading_json['subParts']:
        skill = part['name']
        skill_scores[skill] = part['score']
        skill_evals[skill] = part['response_evaluation']
    
    total_score = sum(skill_scores.values())
    
    with open(file_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            question_id,
            question,
            question_type,
            unit,
            responses,
            skill_scores['Thesis Construction'],
            skill_evals['Thesis Construction'],
            skill_scores['Contextualization'],
            skill_evals['Contextualization'],
            skill_scores['Document Use'],
            skill_evals['Document Use'],
            skill_scores['DBQ Outside Evidence'],
            skill_evals['DBQ Outside Evidence'],
            skill_scores['Document Analysis'],
            skill_evals['Document Analysis'],
            skill_scores['Historical Reasoning'],
            skill_evals['Historical Reasoning'],
            skill_scores['DBQ Complexity'],
            skill_evals['DBQ Complexity'],
            total_score,
            json.dumps(grading_json)
        ])