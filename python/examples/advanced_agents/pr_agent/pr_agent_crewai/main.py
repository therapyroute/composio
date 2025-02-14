import os
from dotenv import load_dotenv
from composio_openai import Action, ComposioToolSet
from crewai import Agent, Crew, Process, Task
from langchain_openai import ChatOpenAI

from composio.client.collections import TriggerEventData

load_dotenv()


# Initialize the ComposioToolSet
composio_toolset = ComposioToolSet()


# Define the tools
pr_agent_tools = composio_toolset.get_tools(
    actions=[
        Action.GITHUB_GET_A_PULL_REQUEST,
        Action.GITHUB_CREATE_A_REVIEW_FOR_A_PULL_REQUEST,
        Action.GITHUB_CREATE_AN_ISSUE,
        Action.SLACK_SENDS_A_MESSAGE_TO_A_SLACK_CHANNEL,
    ]
)

channel_id = os.getenv("CHANNEL_ID", "")
if channel_id == "":
    channel_id = input("Enter Channel id:")
code_review_assistant_prompt = (
    """
        You are an experienced code reviewer.
        Your task is to review the provided file diff and give constructive feedback.

        Follow these steps:
        1. Identify if the file contains significant logic changes.
        2. Summarize the changes in the diff in clear and concise English, within 100 words.
        3. Provide actionable suggestions if there are any issues in the code.

        Once you have decided on the changes, for any TODOs, create a Github issue.
        And send the summary of the PR review to """
    + channel_id
    + """ channel on slack. Slack doesn't have markdown and so send a plain text message.
        Also add the comprehensive review to the PR as a comment.
"""
)



# Initialize the language model
llm = ChatOpenAI(model="gpt-4o")

# Create CrewAI agent
code_reviewer = Agent(
    role="Code Reviewer",
    goal="Review the code successfully",
    backstory="You are an experienced software engineer with a keen eye for code quality and best practices.",
    verbose=True,
    allow_delegation=False,
    tools=pr_agent_tools,
    llm=llm,
)


# Create a task for the agent
def review_code_task(code_to_review):
    return Task(
        description=f"Review the following code changes and provide feedback: {code_to_review}",
        expected_output="A detailed review of the code changes, including any issues, suggestions, and a summary of the changes.",
        agent=code_reviewer,
    )


# Create the crew
code_review_crew = Crew(
    agents=[code_reviewer], tasks=[], verbose=True, process=Process.sequential
)

print("Assistant is ready")

# Create a trigger listener
listener = composio_toolset.create_trigger_listener()


@listener.callback(filters={"trigger_name": "github_pull_request_event"})
def review_new_pr(event: TriggerEventData) -> None:
    # Using the information from Trigger, execute the agent
    code_to_review = str(event.payload)

    # Create a new task for this specific code review
    task = review_code_task(code_to_review)

    # Add the task to the crew and execute
    code_review_crew.tasks = [task]
    result = code_review_crew.kickoff()

    print("Review result:", result)


print("Listener started!")
print("Create a pr to get the review")
listener.wait_forever()
