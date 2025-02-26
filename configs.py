import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

event = {
    "openai_api_key": os.getenv("OPENAI_API_KEY"),
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "output_file": "test_output.csv",
    "google_sheet": {
        "credentials_file": "service_account.json",
        "spreadsheet_id": "1-a03Sr4BCTGh3aotYqvN_rrJt_gZYZNhaY5lMLHZDPw",
        "input_sheet_name": "Inputs",
        "frq_output_sheet_name": "FRQ Responses",
        "saq_grading_sheet_name": "SAQ Grading",
        "leq_grading_sheet_name": "LEQ Grading",
        "dbq_grading_sheet_name": "DBQ Grading",
    },
}


openai_tools = {
    "SAQs": {
        "type": "function",
        "function": {
            "name": "respond_to_saq",
            "description": "Outputs the response for each of the three SAQ parts (a, b, and c) along with an array of fact IDs referenced for each answer.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "answers": {
                        "type": "object",
                        "description": "The responses for each SAQ part, with corresponding fact references.",
                        "properties": {
                            "a": {
                                "type": "object",
                                "description": "Response for part (a).",
                                "properties": {
                                    "response": {
                                        "type": "string",
                                        "description": "The written answer for part (a).",
                                    },
                                    "facts_referenced": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "An array of fact IDs referenced for part (a).",
                                    },
                                },
                                "required": ["response", "facts_referenced"],
                                "additionalProperties": False,
                            },
                            "b": {
                                "type": "object",
                                "description": "Response for part (b).",
                                "properties": {
                                    "response": {
                                        "type": "string",
                                        "description": "The written answer for part (b).",
                                    },
                                    "facts_referenced": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "An array of fact IDs referenced for part (b).",
                                    },
                                },
                                "required": ["response", "facts_referenced"],
                                "additionalProperties": False,
                            },
                            "c": {
                                "type": "object",
                                "description": "Response for part (c).",
                                "properties": {
                                    "response": {
                                        "type": "string",
                                        "description": "The written answer for part (c).",
                                    },
                                    "facts_referenced": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "An array of fact IDs referenced for part (c).",
                                    },
                                },
                                "required": ["response", "facts_referenced"],
                                "additionalProperties": False,
                            },
                        },
                        "required": ["a", "b", "c"],
                        "additionalProperties": False,
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Detailed reasoning for the selection of facts and responses.",
                    },
                },
                "additionalProperties": False,
                "required": ["answers", "reasoning"],
            },
        },
    },
    "LEQs": {
        "type": "function",
        "function": {
            "name": "respond_to_leq",
            "description": "Outputs the response for a long essay question (LEQ) along with an array of fact IDs used and the reasoning behind the response.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "The complete written response for the long essay question.",
                    },
                    "facts_used": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "An array of fact IDs used in the response.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Detailed reasoning for the selection of facts and the constructed response.",
                    },
                },
                "additionalProperties": False,
                "required": ["response", "facts_used", "reasoning"],
            },
        },
    },
    "DBQs": {
        "type": "function",
        "function": {
            "name": "respond_to_dbq",
            "description": "Outputs the response for a document-based question (DBQ) along with an array of fact IDs used and the reasoning behind the response.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "The complete written response for the long essay question.",
                    },
                    "facts_used": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "An array of fact IDs used in the response.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Detailed reasoning for the selection of facts and the constructed response.",
                    },
                },
                "additionalProperties": False,
                "required": ["response", "facts_used", "reasoning"],
            },
        },
    },
}

notes = {
    "SAQs": """
General Scoring Notes
- Each point is earned independently (1 point per SAQ part).
- Accuracy: These scoring guidelines require that students demonstrate historically defensible content knowledge. Given the timed nature of the exam, responses may contain errors that do not detract from their overall quality, as long as the historical content used to advance the argument is accurate.
- Clarity: Exam responses should be considered first drafts and thus may contain grammatical errors. Those errors will not be counted against a student unless they obscure the successful demonstration of the content knowledge, skills, and reasoning processes described below.
- Describe: Provide the relevant characteristics of a specified topic. Description requires more than simply mentioning an isolated term.
- Explain: Provide information about how or why a historical development or process occurs or how or why a relationship exists.
If the SAQ part does not require outside evidence to answer, use the stimulus to inform your response. Do not use any outside knowledge to guide your responses.
""",
    "DBQs": """
The document-based question presents students with seven documents offering various perspectives on a historical development or process. The question requires students to do the following: 
- Respond to the prompt with a historically defensible thesis or claim that establishes a line reasoning
- Describe a broader historical context relevant to the prompt. This means the response must effectively place the argument in broader historical events, developments, or processes beyond the prompt’s time frame
- Support an argument in response to the prompt using at least four documents. 
- You MUST USE at least one additional piece of specific historical evidence (beyond that found in the documents) relevant to the argument about the prompt. You must ONLY use specific outside evidence from the <facts> given. Use the actual fact(s) in the essay, not the fact id(s). Do NOT use the facts that begin with "KC". Output the fact ids used in the "facts_used" part of the JSON.
- For at least two documents, explain how or why the document’s point of view, purpose, historical situation, and/or audience is relevant to an argument.
- Demonstrate a complex understanding of a historical development related to the prompt through sophisticated argumentation and/or effective use of evidence.

This all must be done in essay form; there should be no bullets or titled sections. Ensure all steps are followed. 
""",
    "LEQs": """
The long essay question requires students to do the following: 
- Respond to the prompt with a historically defensible thesis or claim that establishes a line of reasoning.
- Describe a broader historical context relevant to the prompt. This means the response must effectively place the argument in broader historical events, developments, or processes beyond the prompt’s time frame
- Support an argument in response to the prompt using at least two pieces of specific and relevant evidence.
- Demonstrate a complex understanding of a historical development related to the prompt through sophisticated argumentation and/or effective use of evidence.

This all must be done in essay form; there should be no bullets or titled sections. Do not use any outside knowledge to guide your responses, just the <facts> provided.
""",
}

anthropic_tools = {
    "SAQs": {
        "name": "grade_saq",
        "description": 'Grade a student\'s response to a short-answer question (SAQ). The response consists of multiple parts that must be evaluated individually, with an overall assessment. Output must be properly formatted JSON with correct array structures and string escaping. Example output structure: {"subParts": [{"id": "a", "name": "Identify without Stimulus", ...}]}',
        "input_schema": {
            "type": "object",
            "required": ["subParts"],
            "properties": {
                "subParts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "name", "score", "maxScore", "result"],
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "The identifier for the part, e.g., 'a', 'b', or 'c'.",
                            },
                            "name": {
                                "type": "string",
                                "description": "The skill assessed by this part.",
                            },
                            "score": {
                                "type": "integer",
                                "description": "0 if the student did not earn the point, 1 if the student earned the point.",
                            },
                            "result": {
                                "enum": ["CORRECT", "INCORRECT"],
                                "type": "string",
                                "description": "Indicates whether the student’s response has met the scoring criteria. Use 'CORRECT' if the student earned the point and 'INCORRECT' if not.",
                            },
                            "maxScore": {
                                "type": "integer",
                                "description": "Always be 1.",
                            },
                            "question_analysis": {
                                "type": "string",
                                "description": "A breakdown of the SAQ prompt noting the task verb (explain or identify), main topic, relevant time period, and the key elements required for a complete answer, including potential valid examples that align with AP World History guidelines.",
                            },
                            "response_evaluation": {
                                "type": "string",
                                "description": "A detailed critique of the student's response, focusing on historical accuracy, clarity, and how well the student addresses the prompt’s demands. Highlight both strengths and weaknesses in content and presentation.",
                            },
                        },
                    },
                    "description": "An array of response subParts, each representing an individual question or subquestion. All three question parts (a, b, and c) MUST be returned, even if the student doesn't answer the question.",
                }
            },
        },
    },
    "DBQs": {
        "name": "grade_dbq",
        "description": 'Grade a student\'s response to a document-based question (DBQ). The response consists of multiple parts that must be evaluated individually. Output must be properly formatted JSON with correct array structures and string escaping. Example output structure: "subParts": [{"name": "Contextualization", ...}]}',
        "input_schema": {
            "type": "object",
            "required": ["subParts"],
            "properties": {
                "subParts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "name",
                            "question_analysis",
                            "response_evaluation",
                            "score",
                            "result",
                            "maxScore",
                        ],
                        "properties": {
                            "question_analysis": {
                                "type": "string",
                                "description": "A breakdown of the LEQ prompt, main topic, relevant time period, and the key elements required for a complete answer, including potential valid examples that align with AP World History guidelines.",
                            },
                            "response_evaluation": {
                                "type": "string",
                                "description": "A detailed critique of the student's response, focusing on historical accuracy, clarity, and how well the student addresses the prompt’s demands. Highlight both strengths and weaknesses in content and presentation.",
                            },
                            "name": {
                                "type": "string",
                                "description": "The skill assessed by this part.",
                            },
                            "score": {
                                "type": "integer",
                                "description": "0 if the student did not earn the point, 1 if the student earned the point.",
                            },
                            "result": {
                                "enum": ["CORRECT", "INCORRECT"],
                                "type": "string",
                                "description": "Result indicating whether the student's response was correct or incorrect.",
                            },
                            "maxScore": {
                                "type": "integer",
                                "description": "Always be 1 or 2.",
                            },
                        },
                    },
                }
            },
        },
    },
    "LEQs": {
        "name": "grade_leq",
        "description": 'Grade a student\'s response to a long-essay question (LEQ). The response consists of multiple parts that must be evaluated individually. Output must be properly formatted JSON with correct array structures and string escaping. Example output structure: "subParts": [{"name": "Contextualization", ...}]}',
        "input_schema": {
            "type": "object",
            "required": ["subParts"],
            "properties": {
                "subParts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "name",
                            "question_analysis",
                            "response_evaluation",
                            "score",
                            "result",
                            "maxScore",
                        ],
                        "properties": {
                            "question_analysis": {
                                "type": "string",
                                "description": "A breakdown of the LEQ prompt, main topic, relevant time period, and the key elements required for a complete answer, including potential valid examples that align with AP World History guidelines.",
                            },
                            "response_evaluation": {
                                "type": "string",
                                "description": "A detailed critique of the student's response, focusing on historical accuracy, clarity, and how well the student addresses the prompt’s demands. Highlight both strengths and weaknesses in content and presentation.",
                            },
                            "name": {
                                "type": "string",
                                "description": "The skill assessed by this part. Must be either 'Thesis Construction', 'Contextualization', 'LEQ Outside Evidence', 'Historical Reasoning', or 'LEQ Complexity'.",
                            },
                            "score": {
                                "type": "integer",
                                "description": "The number of points the student earned for this part.",
                            },
                            "result": {
                                "enum": ["CORRECT", "INCORRECT"],
                                "type": "string",
                                "description": "Result indicating whether the student's response was correct or incorrect.",
                            },
                            "maxScore": {
                                "type": "integer",
                                "description": "The maximum number of points the student could earn for this part.",
                            },
                        },
                    },
                    "description": "An array of objects, each representing a part of the LEQ that is being graded.",
                }
            },
        },
    },
}
