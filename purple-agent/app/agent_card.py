"""Purple Agent A2A Agent Card."""

AGENT_CARD = {
    "name": "Purple Agent",
    "description": "A versatile AI agent for the AgentX-AgentBeats competition. Capable of reasoning, web search, and task execution.",
    "url": "http://localhost:8020",
    "version": "1.0.0",
    "provider": {
        "organization": "ITMO University",
        "url": "https://itmo.ru",
    },
    "capabilities": {
        "streaming": True,
        "pushNotifications": False,
        "stateTransitionHistory": True,
    },
    "skills": [
        {
            "id": "general-reasoning",
            "name": "General Reasoning",
            "description": "Answer questions, analyze information, and provide detailed explanations on any topic.",
            "tags": ["reasoning", "analysis", "qa"],
            "examples": [
                "Explain the concept of gradient descent",
                "Compare REST and GraphQL APIs",
            ],
        },
        {
            "id": "code-assistance",
            "name": "Code Assistance",
            "description": "Help with code review, debugging, and writing code in multiple languages.",
            "tags": ["code", "programming", "debugging"],
            "examples": [
                "Write a Python function to sort a list",
                "Debug this JavaScript code",
            ],
        },
        {
            "id": "task-planning",
            "name": "Task Planning",
            "description": "Break down complex tasks into actionable steps and create execution plans.",
            "tags": ["planning", "tasks", "organization"],
            "examples": [
                "Plan a microservices migration",
                "Create a study plan for machine learning",
            ],
        },
    ],
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
}
