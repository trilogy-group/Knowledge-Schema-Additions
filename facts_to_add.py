import string
import random
import logging
import json
from anthropic import Anthropic
import configs
import helper_functions
from openai import OpenAI

def generate_uuid(length=4):
    """Generate a unique ID with mixed case and numbers"""
    characters = string.ascii_lowercase + string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def get_facts_from_claude(text):
    """Process text through Claude API and extract facts"""
    client = Anthropic(api_key=configs.event["anthropic_api_key"])
    
    prompt = create_prompt(text)
    schema = get_prompt_schema()
    
    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            tools=[schema]
        )
        
        # Extract tool use from response
        for content in message.content:
            if content.type == 'tool_use':
                return content.input
                
        logging.error("No tool_use found in Claude response")
        return None
        
    except Exception as e:
        logging.error(f"Error calling Claude API: {str(e)}")
        return None

def write_to_process_sheet(sheet_type, curriculum, input_data, output_data):
    """Write prompt input and output to Process sheet for debugging"""
    logging.info(f"Writing {sheet_type} data to Process sheet")
    
    google_sheet_info = configs.event.get("google_sheet")
    if not google_sheet_info:
        logging.error("No Google Sheet information provided")
        return
    
    try:
        # Setup process sheet
        process_sheet = helper_functions.setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            "Consolidation Process"
        )
        
        # Ensure sheet has headers
        existing_values = process_sheet.get_all_values()
        if not existing_values:
            process_sheet.update("A1", [["Timestamp", "Process Step", "Curriculum", "Input", "Output"]])
            existing_values = [["Timestamp", "Process Step", "Curriculum", "Input", "Output"]]
        
        # Add new row
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        next_row = len(existing_values) + 1
        process_sheet.update(f"A{next_row}", [[
            timestamp,
            sheet_type,
            curriculum,
            input_data,
            output_data
        ]])
        
        logging.info(f"Successfully wrote {sheet_type} data to Process sheet")
        
    except Exception as e:
        logging.error(f"Error writing to Process sheet: {str(e)}")

def process_openai_call(prompt, model="o1"):
    """Make a call to OpenAI API with given prompt"""
    client = OpenAI(api_key=configs.event["openai_api_key"])
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort="medium"
        )
        
        content = response.choices[0].message.content
        logging.info("Received response from OpenAI")
        
        return content
    except Exception as e:
        logging.error(f"Error calling OpenAI API: {str(e)}")
        return None

def apply_consolidation_prompt_1(curriculum, facts_list):
    """Apply the first consolidation prompt to the facts list"""
    with open('fact_generator_prompts/consolidation_prompt_1.txt', 'r', encoding='utf-8') as file:
        prompt_template = file.read()
    
    # Format facts list for the prompt
    formatted_facts = "\n".join([f"{fact['id']}: {fact['sources']}: {fact['statement']}" for fact in facts_list])
    
    prompt = prompt_template.format(curriculum=curriculum, full_list=formatted_facts)
    
    result = process_openai_call(prompt)
    if result:
        # Write to process sheet
        write_to_process_sheet("Consolidation Prompt 1", curriculum, formatted_facts, result)
    return result

def apply_consolidation_prompt_2(curriculum, facts_evaluation):
    """Apply the second consolidation prompt to the results from the first prompt"""
    with open('fact_generator_prompts/consolidation_prompt_2.txt', 'r', encoding='utf-8') as file:
        prompt_template = file.read()
    
    
    # Format the prompt with both curriculum and facts_evaluation
    prompt = prompt_template.format(
        curriculum=curriculum,
        fact_list=facts_evaluation
    )
    
    result = process_openai_call(prompt)
    if result:
        # Write to process sheet
        write_to_process_sheet("Consolidation Prompt 2", curriculum, facts_evaluation, result)
    return result


def apply_fact_refinement(curriculum, refined_facts):
    """Apply the fact refinement prompt to the results from the second consolidation"""
    with open('fact_generator_prompts/fact_refinement_prompt.txt', 'r', encoding='utf-8') as file:
        prompt_template = file.read()
      
    prompt = prompt_template.format(curriculum=curriculum, fact_list=refined_facts)
    
    result = process_openai_call(prompt)
    if result:
        # Write to process sheet
        write_to_process_sheet("Fact Refinement", curriculum, refined_facts, result)
    return result

def extract_refined_facts(response_text):
    """Extract the refined facts from the OpenAI response"""  
    try:
        # Look for the JSON structure in the response
        if '"refined_facts":' in response_text:
            # Find the start and end of the JSON portion
            start_idx = response_text.find('"refined_facts":')
            json_text = '{' + response_text[start_idx:]
            # Handle potential trailing text
            if '}' in json_text:
                end_idx = json_text.rindex('}') + 1
                json_text = json_text[:end_idx]
            
            logging.info(f"Found JSON structure, attempting to parse: {json_text[:100]}...")
            
            # Parse the JSON
            data = json.loads(json_text)
            refined_facts = data.get('refined_facts', [])
            
            logging.info(f"Extracted {len(refined_facts)} refined facts")
            if refined_facts:
                for i, fact in enumerate(refined_facts[:3]):  # Log first 3 facts
                    logging.info(f"Sample fact {i+1}: {fact}")
                
                # Write extracted facts to process sheet
                write_to_process_sheet("Extracted Refined Facts", "All", 
                                      json_text, 
                                      json.dumps(refined_facts, indent=2))
            
            return refined_facts
        else:
            # If we can't find the refined_facts field, let's check for alternative formats
            logging.error("Could not find 'refined_facts' in response")
            logging.info("Checking for alternative JSON structures in the response...")
            
            # Try to find any JSON-like structure
            import re
            json_patterns = [r'\{[^{}]*\}', r'\[[^\[\]]*\]']
            potential_jsons = []
            for pattern in json_patterns:
                potential_jsons.extend(re.findall(pattern, response_text))
            
            for i, potential_json in enumerate(potential_jsons[:2]):  # Log first 2 potential JSON structures
                logging.info(f"Potential JSON structure {i+1}: {potential_json[:100]}...")
            
            # Write the failed extraction attempt to process sheet
            write_to_process_sheet("Failed Extraction", "All", 
                                  response_text[:1000], 
                                  "No refined_facts found. Potential JSON: " + 
                                  ", ".join([pj[:200] for pj in potential_jsons[:2]]))
            
            return []
    except Exception as e:
        logging.error(f"Error extracting refined facts: {str(e)}")
        logging.info(f"JSON text that failed to parse: {json_text[:300]}..." if locals().get('json_text') else "No JSON text captured")
        
        # Write the error to process sheet
        write_to_process_sheet("Extraction Error", "All", 
                              response_text[:1000], 
                              f"Error: {str(e)}")
        
        return []

def process_fact_consolidation():
    """Process facts from Fact Outputs sheet through consolidation and refinement pipeline"""
    logging.info("Starting fact consolidation process")
    
    # Setup Google Sheets
    google_sheet_info = configs.event.get("google_sheet")
    if not google_sheet_info:
        logging.error("No Google Sheet information provided")
        return
    
    try:
        # Setup fact outputs sheet to read from
        fact_output_sheet = helper_functions.setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            "Fact Outputs"
        )
        
        # Setup refined facts sheet to write to
        refined_facts_sheet = helper_functions.setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            "Refined Facts"
        )
        
        # Setup processed fact IDs sheet to track which facts have been processed
        processed_ids_sheet = helper_functions.setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            "Processed Fact IDs"
        )
        
        # Ensure processed fact IDs sheet has headers
        processed_ids_values = processed_ids_sheet.get_all_values()
        if not processed_ids_values:
            processed_ids_sheet.update("A1", [["Original Fact ID", "Curriculum", "Processed Date"]])
            processed_ids_values = [["Original Fact ID", "Curriculum", "Processed Date"]]
        
        # Get already processed original fact IDs
        processed_original_fact_ids = set()
        for row in processed_ids_values[1:]:  # Skip header
            if len(row) >= 1:  # Ensure the row has at least the fact ID
                processed_original_fact_ids.add(row[0])
        
        # Ensure refined facts sheet has headers
        existing_refined_values = refined_facts_sheet.get_all_values()
        if not existing_refined_values:
            refined_facts_sheet.update("A1", [["Fact ID", "Curriculum", "Refined Fact Statement"]])
            existing_refined_values = [["Fact ID", "Curriculum", "Refined Fact Statement"]]
        
        # Get all values from fact outputs sheet
        output_values = fact_output_sheet.get_all_values()
        if len(output_values) < 2:
            logging.warning("Fact Outputs sheet has no data or only headers")
            return
            
        # Extract headers and data
        headers = output_values[0]
        data_rows = output_values[1:]
        
        # Check if we have the right columns
        required_cols = ["Topic", "Text", "Fact ID", "Fact Statement", "Curriculum"]
        missing_cols = [col for col in required_cols if col not in headers]
        if missing_cols:
            logging.error(f"Fact Outputs sheet is missing required columns: {missing_cols}")
            return
            
        # Get column indices
        topic_idx = headers.index("Topic")
        fact_id_idx = headers.index("Fact ID")
        fact_stmt_idx = headers.index("Fact Statement")
        curriculum_idx = headers.index("Curriculum") if "Curriculum" in headers else None
        
        # Group facts by curriculum
        facts_by_curriculum = {}
        
        # Track original fact IDs for each curriculum to record as processed later
        original_ids_by_curriculum = {}
        
        for row in data_rows:
            if len(row) <= max(topic_idx, fact_id_idx, fact_stmt_idx):
                logging.warning(f"Skipping row with insufficient columns: {row}")
                continue
            
            fact_id = row[fact_id_idx]
            fact_stmt = row[fact_stmt_idx]
            curriculum = row[curriculum_idx] if curriculum_idx is not None else "default"
            
            # Skip if this fact ID has already been processed
            if fact_id in processed_original_fact_ids:
                logging.info(f"Skipping already processed fact ID: {fact_id}")
                continue
                
            if curriculum not in facts_by_curriculum:
                facts_by_curriculum[curriculum] = []
                original_ids_by_curriculum[curriculum] = []
                
            # Assuming the sources information is not available, we'll use empty string
            facts_by_curriculum[curriculum].append({
                "id": fact_id,
                "sources": "",
                "statement": fact_stmt
            })
            
            # Track original fact ID to mark as processed later
            original_ids_by_curriculum[curriculum].append(fact_id)
        
        # Process each curriculum group
        all_refined_facts = []
        processed_ids_to_add = []
        import datetime
        
        for curriculum, facts_list in facts_by_curriculum.items():
            if not facts_list:
                continue
            
            logging.info(f"Curriculum: {curriculum[:50]}")    
            logging.info(f"Number of facts to process: {len(facts_list)}")
            logging.info(f"First few fact IDs: {[fact['id'] for fact in facts_list[:5]]}")
            
            # Step 1: Apply consolidation prompt 1
            facts_evaluation = apply_consolidation_prompt_1(curriculum, facts_list)
            if not facts_evaluation:
                logging.error(f"Failed to get facts evaluation for curriculum {curriculum[:50]}")
                continue
                
            # Step 2: Apply consolidation prompt 2
            consolidated_facts = apply_consolidation_prompt_2(curriculum, facts_evaluation)
            if not consolidated_facts:
                logging.error(f"Failed to get consolidated facts for curriculum {curriculum[:50]}")
                continue
                
            # Step 3: Apply fact refinement prompt
            refined_result = apply_fact_refinement(curriculum, consolidated_facts)
            if not refined_result:
                logging.error(f"Failed to get refined facts for curriculum {curriculum[:50]}")
                continue
                
            # Extract refined facts from the response
            refined_facts = extract_refined_facts(refined_result)
            if not refined_facts:
                logging.error(f"Failed to extract refined facts for curriculum {curriculum[:50]}")
                continue
                
            # Add curriculum to refined facts and generate new IDs
            output_rows = []
            for fact in refined_facts:
                new_fact_id = f"a_{generate_uuid()}"
                fact_statement = fact.get("statement", "")  # Try statement field first
                if not fact_statement:
                    fact_statement = fact.get("fact", "")   # Try fact field as backup
                
                logging.info(f"Refined fact: {new_fact_id} - {fact_statement[:100]}...")
                
                output_rows.append([
                    new_fact_id,
                    curriculum,
                    fact_statement
                ])
                
            all_refined_facts.extend(output_rows)
            
            # Mark original fact IDs as processed
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            for original_id in original_ids_by_curriculum[curriculum]:
                processed_ids_to_add.append([
                    original_id,
                    curriculum,
                    current_date
                ])
        
        # Write all refined facts to the sheet
        if all_refined_facts:
            next_row = len(existing_refined_values) + 1
            refined_facts_sheet.update(f"A{next_row}", all_refined_facts)
            logging.info(f"Added {len(all_refined_facts)} refined facts to Refined Facts sheet")
        else:
            logging.info("No new refined facts were generated")
            
        # Write processed original fact IDs to the tracking sheet
        if processed_ids_to_add:
            next_row = len(processed_ids_values) + 1
            processed_ids_sheet.update(f"A{next_row}", processed_ids_to_add)
            logging.info(f"Added {len(processed_ids_to_add)} fact IDs to Processed Fact IDs sheet")
            
    except Exception as e:
        logging.error(f"Error processing fact consolidation: {str(e)}")

def process_fact_inputs():
    """Read from Fact Inputs sheet, process through Claude, and write to Fact Outputs sheet"""
    logging.info("Starting fact generation process")
    
    # Setup Google Sheets
    google_sheet_info = configs.event.get("google_sheet")
    if not google_sheet_info:
        logging.error("No Google Sheet information provided")
        return
    
    try:
        # Setup input sheet
        input_sheet = helper_functions.setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            "Fact Inputs"
        )
        
        # Setup output sheet
        output_sheet = helper_functions.setup_google_sheet(
            google_sheet_info["credentials_file"],
            google_sheet_info["spreadsheet_id"],
            "Fact Outputs"
        )
        
        # Get all values from input sheet
        input_values = input_sheet.get_all_values()
        if len(input_values) < 2:  # Check if we have headers and at least one row
            logging.warning("Fact Inputs sheet has no data or only headers")
            return
            
        # Extract headers and data
        headers = input_values[0]
        data_rows = input_values[1:]
        
        # Check if we have the right columns
        if "Topic" not in headers or "Text" not in headers:
            logging.error("Fact Inputs sheet must have 'Topic' and 'Text' columns")
            return
            
        topic_index = headers.index("Topic")
        text_index = headers.index("Text")
        curriculum_index = headers.index("Curriculum") if "Curriculum" in headers else None
        
        # Read existing output data to avoid duplicates
        existing_values = output_sheet.get_all_values()
        if not existing_values:
            # Add Curriculum to the headers if it exists in input
            output_headers = ["Topic", "Text", "Fact ID", "Fact Statement"]
            if curriculum_index is not None:
                output_headers.append("Curriculum")
            output_sheet.update("A1", [output_headers])
            existing_values = [output_headers]
        
        # Track which Topic-Text combinations have already been processed
        processed_combinations = set()
        for row in existing_values[1:]:  # Skip header
            if len(row) >= 2:  # Ensure the row has at least topic and text
                processed_combinations.add((row[0], row[1]))
        
        # Process each row
        output_rows = []
        
        for row in data_rows:
            if len(row) <= max(topic_index, text_index):
                logging.warning(f"Skipping row with insufficient columns: {row}")
                continue
                
            topic = row[topic_index]
            text = row[text_index]
            curriculum = row[curriculum_index] if curriculum_index is not None else ""
            
            # Skip if this Topic-Text combination has already been processed
            if (topic, text) in processed_combinations:
                logging.info(f"Skipping already processed topic-text: {topic}")
                continue
                
            if not text:
                logging.warning(f"Skipping row with empty text for topic {topic}")
                continue
                
            logging.info(f"Processing text for topic: {topic}")
            
            # Get facts from Claude
            result = get_facts_from_claude(text)
            if not result:
                logging.error(f"Failed to get facts for topic {topic}")
                continue
                
            # Extract statements from required_concepts
            facts_added = False
            if "required_concepts" in result:
                for concept in result["required_concepts"]:
                    if "statement" in concept:
                        fact_id = f"a_{generate_uuid()}"
                        fact_row = [
                            topic,
                            text,
                            fact_id,
                            concept["statement"]
                        ]
                        # Add curriculum if it exists
                        if curriculum_index is not None:
                            fact_row.append(curriculum)
                        output_rows.append(fact_row)
                        facts_added = True
            
            # Mark this combination as processed (even if no facts were added)
            processed_combinations.add((topic, text))
            
            if not facts_added:
                logging.warning(f"No facts were generated for topic {topic}")
        
        # Append all rows to output sheet
        if output_rows:
            next_row = len(existing_values) + 1
            output_sheet.update(f"A{next_row}", output_rows)
            logging.info(f"Added {len(output_rows)} facts to Fact Outputs sheet")
        else:
            logging.info("No new facts were generated")
            
    except Exception as e:
        logging.error(f"Error processing fact inputs: {str(e)}")

def create_prompt(input_text):
    with open('fact_generator_prompts/textbook_fact_generation_prompt.txt', 'r', encoding='utf-8') as file:
        prompt_template = file.read()

    return prompt_template.format(input_text=input_text)

def get_prompt_schema():
    """Returns the schema for the Claude API response"""
    return {
        "name": "get_required_facts_list",
        "description": "Get a list of facts relevant to the given content",
        "input_schema": {
            "type": "object",
            "properties": {
                "content_breakdown": {
                    "type": "string",
                    "description": "A detailed breakdown of the content"
                },
                "required_concepts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "statement": {
                                "type": "string",
                                "description": "Clear and concise statement of specific knowledge"
                            },
                            "justification": {
                                "type": "string",
                                "description": "Why this concept is necessary to understand the input text"
                            }
                        },
                        "required": ["statement", "justification"]
                    },
                    "description": "Array of required concept objects"
                }
            },
            "required": [
                "content_breakdown",
                "required_concepts"
            ]
        }
    }

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    process_fact_inputs()
    # After generating facts, run the consolidation pipeline
    process_fact_consolidation()