import logging
import json
import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI
from anthropic import Anthropic
import configs
import helper_functions as hf

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def setup_sheets():
    """Sets up and returns both input and output Google Sheets worksheets."""
    credentials_file = "service_account.json"
    spreadsheet_id = configs.event.get("google_sheet").get("spreadsheet_id")
    
    # Get input sheet
    input_sheet_name = "Refined Facts"
    input_sheet = hf.setup_google_sheet(credentials_file, spreadsheet_id, input_sheet_name)
    
    # Setup output sheet (or create if doesn't exist)
    output_sheet_name = "Final Facts"
    try:
        output_sheet = hf.setup_google_sheet(credentials_file, spreadsheet_id, output_sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # Create the worksheet if it doesn't exist
        client = gspread.authorize(Credentials.from_service_account_file(
            credentials_file, 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        ))
        spreadsheet = client.open_by_key(spreadsheet_id)
        output_sheet = spreadsheet.add_worksheet(title=output_sheet_name, rows=1000, cols=11)  # Added more columns for metadata
        
        # Add header row with metadata columns
        output_sheet.update('A1:K1', [['Unit', 'Fact ID', 'Fact Statement', 'Redundant', 'Reasoning', 
                                      'Classification', 'Definition', 'Date', 'Theme', 'Cluster', 'LO Mapping']])
    
    return input_sheet, output_sheet

def check_redundancy(fact_id, fact_statement, unit, existing_facts):
    """
    Checks if a fact is redundant with existing facts from the same unit.
    Returns a tuple (is_redundant, reasoning).
    """
    # Setup OpenAI client
    client = OpenAI(api_key=configs.event["openai_api_key"])
    
    # Create prompt
    prompt = f"""
You are analyzing facts for a history curriculum. Your job is to determine if a new fact is redundant with existing facts.

NEW FACT ID: {fact_id}
NEW FACT: {fact_statement}

EXISTING FACTS FROM UNIT {unit}:
{existing_facts}

Is the new fact redundant with any of the existing facts? Consider the following:
1. Facts are redundant if they express essentially the same information, even if worded differently.
2. Facts are NOT redundant if they cover related topics but provide distinct information.
3. Facts are NOT redundant if they mention the same historical entity but provide different details or perspectives.

Please provide:
1. A judgment of TRUE (if redundant) or FALSE (if not redundant)
2. A brief explanation of your reasoning (max 1-2 sentences)

Format your response as a JSON object:
{{
  "is_redundant": true/false,
  "reasoning": "Your explanation here"
}}
"""

    try:
        response = client.chat.completions.create(
            model="o1",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        logging.info(f"Received redundancy check response for fact {fact_id}")
        
        # Parse JSON response
        result = json.loads(content)
        return result["is_redundant"], result["reasoning"]
    except Exception as e:
        logging.error(f"Error checking redundancy for fact {fact_id}: {str(e)}")
        return None, f"Error: {str(e)}"

def generate_metadata(fact_statement, curriculum):
    """
    Generate metadata for a fact using the Anthropic API with the get_fact_metadata tool.
    Returns a dictionary with metadata fields.
    """
    # Setup Anthropic client
    client = Anthropic(api_key=configs.event["anthropic_api_key"])
    
    
    # Define the metadata generation tool
    get_fact_metadata_tool = {
        "name": "get_fact_metadata",
        "description": "Get metadata attributes for a historical fact",
        "input_schema": {
            "type": "object",
            "properties": {
                "classification": {
                    "type": "string",
                    "enum": ["Essential", "Supporting"],
                    "description": "Whether this is an essential or supporting fact"
                },
                "definition": {
                    "type": "boolean",
                    "description": "Whether this fact represents a definition"
                },
                "date": {
                    "type": "string",
                    "description": "The relevant date or time period"
                },
                "theme": {
                    "type": "string",
                    "enum": ["TEC", "ENV", "ECN", "GOV", "SIO", "CDI"],
                    "description": "The primary historical theme"
                },
                "cluster": {
                    "type": "string",
                    "description": "The cluster"
                },
                "learning_objective": {
                    "type": "string",
                    "description": "The learning objective"
                },
                "reasoning": {
                    "type": "string",
                    "description": "The reasoning for each element of the metadata that was created"
                }
            },
            "required": ["classification", "definition", "date", "theme", "cluster", "learning_objective", "reasoning"]
        }
    }
    
    # Load the metadata generation prompt template
    try:
        with open('fact_generator_prompts/metadata_generation_prompt.txt', 'r', encoding='utf-8') as file:
            prompt_template = file.read()
            
        # Replace placeholders in the template
        prompt = prompt_template.replace("{curriculum}", curriculum)
        prompt = prompt.replace("{statement}", fact_statement)
    except Exception as e:
        logging.error(f"Error loading or processing metadata prompt template: {str(e)}")

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=8000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            tools=[get_fact_metadata_tool]
        )
        
        for i, content in enumerate(message.content):
            if content.type == 'tool_use':
                metadata = content.input
        
        if not metadata:
            logging.error("No metadata tool use found in response")
            return {
                "classification": "Error",
                "definition": "Error",
                "date": "Error",
                "theme": "Error",
                "cluster": "Error",
                "learning_objective": "Error"
            }
        
        # Convert definition from boolean to string for spreadsheet compatibility
        if isinstance(metadata.get("definition"), bool):
            metadata["definition"] = str(metadata["definition"]).lower()
        
        # Map learning_objective to lo_mapping to match our expected output structure
        metadata["learning_objective"] = metadata.pop("learning_objective", "")
            
        return metadata
        
    except Exception as e:
        logging.error(f"Error generating metadata: {str(e)}")
        return {
            "classification": "Error",
            "definition": "Error",
            "date": "Error",
            "theme": "Error",
            "cluster": "Error",
            "learning_objective": "Error"
        }

def process_facts():
    """
    Main function to process facts from input sheet and append results to output sheet.
    """
    # Setup sheets
    input_sheet, output_sheet = setup_sheets()
    
    # Get all records from input sheet
    input_records = input_sheet.get_all_records()
    logging.info(f"Found {len(input_records)} records in the input sheet")
    
    # Get all records from the output sheet to check for already processed facts
    existing_output_data = output_sheet.get_all_records()
    processed_fact_ids = {row.get('Fact ID') for row in existing_output_data if row.get('Fact ID')}
    
    # Process each record
    for record in input_records:
        # Extract data from record
        fact_id = record.get('Fact ID', '')
        fact_statement = record.get('Refined Fact Statement', '')
        unit = record.get('Unit', '')
        curriculum = record.get('Curriculum', '')

        # Skip if any required field is missing
        if not fact_id or not fact_statement or not unit:
            logging.warning(f"Missing required data for record: {record}")
            continue
        
        # Skip if fact has already been processed
        if fact_id in processed_fact_ids:
            logging.info(f"Fact {fact_id} already processed, skipping")
            continue
        
        # Get existing facts for the unit
        try:
            existing_facts = hf.get_facts_for_unit(unit)
            facts_text = "\n".join([f"- {fact}" for fact in existing_facts])
        except Exception as e:
            logging.error(f"Error getting facts for unit {unit}: {str(e)}")
            facts_text = "No existing facts found."
        
        # Check for redundancy
        is_redundant, reasoning = check_redundancy(fact_id, fact_statement, unit, facts_text)
        
        if is_redundant is not None:
            # Initialize values for metadata fields
            metadata = {
                "classification": "",
                "definition": "",
                "date": "",
                "theme": "",
                "cluster": "",
                "learning_objective": ""
            }
            
            # If not redundant, generate metadata
            if is_redundant is False:
                logging.info(f"Fact {fact_id} is not redundant, generating metadata")
                metadata = generate_metadata(fact_statement, curriculum)
            
            # Prepare row for output sheet with metadata
            new_row = [
                unit, 
                fact_id, 
                fact_statement, 
                str(is_redundant), 
                reasoning,
                metadata.get("classification", ""),
                metadata.get("definition", ""),
                metadata.get("date", ""),
                metadata.get("theme", ""),
                metadata.get("cluster", ""),
                metadata.get("learning_objective", "")
            ]
            
            # Append to output sheet
            output_sheet.append_row(new_row)
            logging.info(f"Added fact {fact_id} to output sheet with metadata")
            
            # Add to processed facts to avoid processing again in this run
            processed_fact_ids.add(fact_id)
        else:
            logging.error(f"Failed to check redundancy for fact {fact_id}")

if __name__ == "__main__":
    logging.info("Starting fact finalization process")
    process_facts()
    logging.info("Fact finalization process completed")
