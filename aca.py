from openai import OpenAI, AssistantEventHandler
import json
from typing_extensions import override

model = "gpt-4-turbo" # todo: there is error with gpt-4o + assistant api ver 1
client = OpenAI(
    api_key='add_your_api_key_here',
    default_headers={"OpenAI-Beta": "assistants=v2"}
)

# 1. detect assist's role
role_extractor_path = './prompts/1_role_matcher.prompt'
with open(role_extractor_path, 'r') as file:
    role_extractor_prompt = file.read().strip()

task = input("Your task: ")

completion = client.chat.completions.create(
    model=model,
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": role_extractor_prompt},
        {"role": "user", "content": task}
    ]
)
json_role = json.loads(completion.choices[0].message.content)
role = json_role['role']
print(f"--- 1.Role: DETECTED '{role}'")

# 2. create new assist's prompt (instruction)
new_agent_prompt_path = './prompts/2_agent_prompt_creator.prompt'
with open(new_agent_prompt_path, 'r') as file:
    agent_creator_prompt = file.read().strip()

completion = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": agent_creator_prompt},
        {"role": "user", "content": f"###\nRole: {role}"}
    ]
)
instructions = completion.choices[0].message.content
# print(f"--- 2.Instruction: \n{instructions}")
print("--- 2.Instruction: CREATED")

# 3. create new assistant
assistant = client.beta.assistants.create(
  name=f"{role} Assistant",
  instructions=instructions,
  tools=[{"type": "code_interpreter"}], # todo: implement tools logic later (+files)
  model=model,
)
print(f"--- 3.New '{role}' Assistant: CREATED with id '{assistant.id}'")

# 4. solve the problem using the new assistant
thread = client.beta.threads.create()
message = client.beta.threads.messages.create(
  thread_id=thread.id,
  role="user",
  content=task
)

# with streaming
class EventHandler(AssistantEventHandler):
    @override
    def on_text_created(self, text) -> None:
        print(f"\n--- {role} Assistant > \n", end="", flush=True)

    @override
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)

    def on_tool_call_created(self, tool_call):
        print(f"\n--- {role} Assistant > \n{tool_call.type}\n", flush=True)

    def on_tool_call_delta(self, delta, snapshot):
        if delta.type == 'code_interpreter':
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\n--- {role} Assistant(output) > \n", flush=True)
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)


with client.beta.threads.runs.stream(
        thread_id=thread.id,
        assistant_id=assistant.id,
        # instructions="",
        event_handler=EventHandler(),
) as stream:
    stream.until_done()

####
while True: # todo: don't use it IRL
    new_input = input("\n" + ("-" * 30) + "\nUser (or 'quit' to exit): ")
    if new_input.lower() == 'quit':
        break
    client.beta.threads.messages.create(
      thread_id=thread.id,
      role="user",
      content=new_input
    )

    with client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=assistant.id,
            # instructions="",
            event_handler=EventHandler(),
    ) as stream:
        stream.until_done()
