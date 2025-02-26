import csv
import json
import time
import logging
import multiprocessing
from openai import OpenAI
from anthropic import Anthropic
import configs
import helper_functions

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def process_frq(question_tuple, output_path, lock, max_retries=5):
    """
    Process a single FRQ question using OpenAI API and write results to the output file.
    """
    # Initialize OpenAI client inside the process
    openai_client = OpenAI(api_key=configs.event["openai_api_key"])
    
    question, question_type, unit, question_id = question_tuple
    
    try:
        # Get facts for this specific question's unit
        facts = helper_functions.get_facts_for_unit(unit)
        
        instructions = f"""
            Using JUST the following facts, respond to the inputted AP World History free-response question (FRQ). Consider the following scoring notes for these types of questions:
            <notes>
            {configs.notes[question_type]}
            </notes>
            <facts>
            {facts}
            </facts>
            Make a note of the fact ids used as you respond to the FRQ. If the question has multiple parts (i.e., a, b, and c), none of the parts can have the same answer.
            """
        
        tools = [configs.openai_tools[question_type]]
        messages = [
            {"role": "developer", "content": instructions},
            {"role": "user", "content": [{"type": "text", "text": question}]},
        ]
        
        for retry_count in range(max_retries):
            try:
                completion = openai_client.chat.completions.create(
                    model="o3-mini", 
                    messages=messages, 
                    tools=tools, 
                    tool_choice="auto", 
                    reasoning_effort="high"
                )
                
                # Extract function arguments
                function_args_str = completion.choices[0].message.tool_calls[0].function.arguments
                function_args = json.loads(function_args_str)
                
                # Format the response data
                responses, facts_referenced, combined = helper_functions.format_response_data(function_args, question_type)
                
                # Write to output file with lock for thread safety
                with lock:
                    with open(output_path, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            question_id,
                            question,
                            question_type,
                            unit,
                            responses,
                            facts_referenced,
                            combined,
                            function_args["reasoning"],
                            json.dumps(function_args)
                        ])
                
                logging.info(f"Successfully processed question ID {question_id}")
                return function_args
                
            except Exception as e:
                logging.error(f"Attempt {retry_count + 1} failed for question ID {question_id}: {str(e)}")
                if retry_count < max_retries - 1:
                    logging.info(f"Retrying question ID {question_id} after a short delay...")
                    time.sleep(2)
                continue
        
        logging.error(f"Failed to process question ID {question_id} after {max_retries} attempts")
        return None
        
    except Exception as e:
        logging.error(f"Error processing question ID {question_id} of type '{question_type}' for unit {unit}: {str(e)}")
        return None

def process_grading(row, output_files, grading_prompts, max_retries=3):
    """Process a single FRQ response for grading using Anthropic API."""
    # Initialize Anthropic client inside the process
    anthropic_client = Anthropic(api_key=configs.event["anthropic_api_key"])
    
    question_id = row['Question ID']
    question = row['Question']
    question_type = row['Question Type']
    unit = row['Unit']
    response = row['Responses']

    # Get the correct tool and prompt for this question type
    if question_type == 'SAQs':
        file_path, headers = output_files['SAQs']
    elif question_type == 'LEQs':
        file_path, headers = output_files['LEQs']
    elif question_type == 'DBQs':
        file_path, headers = output_files['DBQs']
    else:
        logging.error(f"Unknown question type: {question_type}")
        return
    
    if question_type not in grading_prompts:
        logging.error(f"No grading prompt found for {question_type}")
        return
                
    prompt_template = grading_prompts[question_type]
    formatted_prompt = prompt_template.replace("{question}", question).replace("{response}", response)

    tools = [configs.anthropic_tools[question_type]]

    
    for attempt in range(1, max_retries + 1):
        try:
            # Call Anthropic API with prompt
            message = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8000,
                temperature=0,
                messages=[{"role": "user", "content": formatted_prompt}],
                tools=tools
            )

            # Log the response structure for debugging
            logging.info(f"Received response for {question_id}: {len(message.content)} content blocks")
            
            tool_use_found = False
            for i, content in enumerate(message.content):
                if content.type == 'tool_use':
                    tool_use_found = True
                    grading_json = content.input
                    
                    # Write the grading results based on question type
                    if question_type == 'SAQs':
                        helper_functions.write_saq_grade(file_path, question_id, question, question_type, unit, response, grading_json)
                    elif question_type == 'LEQs':
                        helper_functions.write_leq_grade(file_path, question_id, question, question_type, unit, response, grading_json)
                    elif question_type == 'DBQs':
                        helper_functions.write_dbq_grade(file_path, question_id, question, question_type, unit, response, grading_json)
                    
                    logging.info(f"Successfully graded question ID {question_id}")
                    return True
            
            if not tool_use_found:
                logging.error(f"No tool_use found in response for question ID {question_id}, type {question_type}")
                logging.error(f"Response content types: {[c.type for c in message.content]}")
                logging.error(f"Full response: {message}")
            
        except Exception as e:
            logging.error(f"Attempt {attempt} failed for grading question ID {question_id}: {str(e)}")
            if attempt < max_retries:
                logging.info(f"Retrying grading for question ID {question_id} after a short delay...")
                time.sleep(2 * attempt)  # Exponential backoff
            else:
                logging.error(f"Failed to grade question ID {question_id} after {max_retries} attempts")
    
    return False
def generate_frq_responses(question_data, frq_output_path):
    """
    Generate FRQ responses using multiprocessing.
    """
    with multiprocessing.Manager() as manager:
        lock = manager.Lock()
        pool = multiprocessing.Pool(processes=5, maxtasksperchild=5)
        
        async_results = []
        for qt in question_data:
            result = pool.apply_async(
                process_frq,
                args=(qt, frq_output_path, lock)
            )
            async_results.append(result)
        
        # Wait for all processes to complete
        for result in async_results:
            try:
                result.get()  # Ensures we catch any exceptions in child processes
            except Exception as e:
                logging.error(f"An error occurred during FRQ processing: {str(e)}")
        
        pool.close()
        pool.join()
    
    logging.info(f"Completed FRQ response generation for {len(question_data)} questions")

def grade_frq_responses(frq_output_path, output_files):
    """
    Grade FRQ responses using multiprocessing.
    """
    # Load grading prompts
    grading_prompts = {}
    for question_type in ['SAQs', 'LEQs', 'DBQs']:
        prompt_file = f"grading_prompts/{question_type.lower()[:-1]}_grading.txt"
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                grading_prompts[question_type] = f.read()
            logging.info(f"Loaded grading prompt for {question_type}")
        except Exception as e:
            logging.error(f"Failed to load grading prompt for {question_type}: {str(e)}")
    
    # Read FRQ responses from Google Sheet instead of CSV
    try:
        google_sheet_info = configs.event.get("google_sheet")
        if not google_sheet_info:
            logging.error("No Google Sheet information found for reading FRQ responses")
            return
            
        frq_sheet = helper_functions.setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            google_sheet_info["frq_output_sheet_name"]
        )
        
        # Get all data including headers
        all_data = frq_sheet.get_all_values()
        if len(all_data) < 2:  # Check if we have headers and at least one row
            logging.warning("FRQ Google Sheet has no data or only headers")
            return
            
        # Extract headers and data
        headers = all_data[0]
        data_rows = all_data[1:]
        
        # Convert to list of dictionaries (like DictReader)
        rows = []
        for row_data in data_rows:
            row_dict = {headers[i]: row_data[i] for i in range(min(len(headers), len(row_data)))}
            rows.append(row_dict)
            
        logging.info(f"Read {len(rows)} rows from Google Sheet '{google_sheet_info['frq_output_sheet_name']}'")
            
        # Count question types for debugging
        saq_count = sum(1 for row in rows if row['Question Type'] == 'SAQs')
        leq_count = sum(1 for row in rows if row['Question Type'] == 'LEQs')
        dbq_count = sum(1 for row in rows if row['Question Type'] == 'DBQs')
        logging.info(f"Found {saq_count} SAQs, {leq_count} LEQs, and {dbq_count} DBQs to grade")
        
    except Exception as e:
        logging.error(f"Failed to read FRQ responses from Google Sheet: {str(e)}")
        logging.info("Falling back to local CSV file")
        
        # Fallback to CSV if Google Sheet fails
        try:
            with open(frq_output_path, "r", encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            logging.info(f"Read {len(rows)} rows from {frq_output_path}")
        except Exception as csv_e:
            logging.error(f"Failed to read FRQ responses from {frq_output_path}: {str(csv_e)}")
            return
    
    if not rows:
        logging.warning("No FRQ responses found to grade")
        return
    
    with multiprocessing.Pool(processes=3, maxtasksperchild=3) as pool:
        async_results = []
        for row in rows:
            result = pool.apply_async(
                process_grading,
                args=(row, output_files, grading_prompts)
            )
            async_results.append(result)
        
        # Wait for all processes to complete
        for result in async_results:
            try:
                result.get()  # Ensures we catch any exceptions in child processes
            except Exception as e:
                logging.error(f"An error occurred during grading: {str(e)}")
    
    logging.info(f"Completed grading for {len(rows)} FRQ responses")

def main():
    """
    Main orchestration function.
    """
    # Setup output files
    frq_output_path, output_files = helper_functions.setup_output_files()
    
    # Get input data (either from Google Sheets or fallback to CSV)
    records = helper_functions.get_input_sheet()
    
    question_data = helper_functions.get_question_inputs(records)

    if not question_data:
        logging.error("No questions found to process")
        return
    
    # Generate FRQ responses
    generate_frq_responses(question_data, frq_output_path)
    
    # Write FRQ responses to Google Sheet
    helper_functions.write_to_frq_sheet(frq_output_path)
    logging.info("FRQ responses written to Google Sheet")
    
    # Grade FRQ responses
    grade_frq_responses(frq_output_path, output_files)
    
    # Write grading results to Google Sheet
    helper_functions.write_to_grading_sheet(output_files)
    logging.info("Grading results written to Google Sheet")
    
    logging.info("Processing complete")

if __name__ == "__main__":
    main()