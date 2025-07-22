from dotenv import load_dotenv
from typing import Annotated, Literal

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages  
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field 
from typing_extensions import TypedDict
import os

load_dotenv()


# using gemini llm to generate responses, classify also...
llm = ChatGoogleGenerativeAI(
  model="gemini-1.5-flash",
  google_api_key=os.getenv("GOOGLE_API_KEY")
)


# defining how the model should except the message type, that should be exactly one of those labels
class MessageClassifier(BaseModel):
  message_type: Literal["emotional" , "logical"] = Field(
    ...,
    description = "Classify if the message requires an emotional (therapist) or logical response."
  )

# my state is a dictionary with a messages, message type classified with the classifier LLM, then the next agent that should handle the request
class State(TypedDict):
  messages: Annotated[list, add_messages]
  message_type : str | None
  next : str | None


# DEALING WITH THE NODES 
## Classification node
def classifyMessage(state: State):
  """
  well the goal is to classify weather the user input is emotional or logical, so we can redirected to the appropiate agent
  """

  last_message = state["messages"][-1]
  # uses structured_output() to force the model to return one of the two valid labels ("emotional", "logical")
  classifier_llm = llm.with_structured_output(MessageClassifier)

  result = classifier_llm.invoke(
    [
      {
        "role" : "system",
        "content" : """
            Classify the user message as either:
            - 'emotional': if it asks for emotional support, therapy, deals with feelings, or personal problems
            - 'logical': if it asks for facts, information, logical analysis, or practical solutions
            """
      },
      {
        "role" : "user",
        "content" : last_message.content
      }
    ]
  )

  return {"message_type" : result.message_type}

## Router node
def router(state: State):
  message_type = state.get("message_type", "logical")
  next_node = "emotionalAgent" if message_type == "emotional" else "logicalAgent"
  return {**state, "next": next_node}

  ## **state means : take everything from state and put it here → copy all state, then set "next" to next_node.


# emotional Agent node 
def emotionalAgent(state: State):

  messages = [
      {"role": "system",
        "content": """You are a compassionate therapist. Focus on the emotional aspects of the user's message.
                      Show empathy, validate their feelings, and help them process their emotions.
                      Ask thoughtful questions to help them explore their feelings more deeply.
                      Avoid giving logical solutions unless explicitly asked.

                      SO BEFORE YOU START ANSWERING, START WITH : As a therapist Assistant...
                      """
    }] + state["messages"]

  reply = llm.invoke(messages)

  # Append assistant response to messages
  updated_messages = state["messages"] + [{"role": "assistant", "content": reply.content}]
  
  return {"messages" : updated_messages}

def logicalAgent(state: State):
    # Prepend the system prompt to full history
    messages = [
        {
            "role": "system",
            "content": """You are a purely logical assistant. Focus only on facts and information.
            Provide clear, concise answers based on logic and evidence.
            Do not address emotions or provide emotional support.
            Be direct and straightforward in your responses.

            SO BEFORE YOU START ANSWERING, START WITH : As a logical Assistant...
            """
        }
    ] + state["messages"]  # ✅ Keep the full conversation

    # Generate response
    reply = llm.invoke(messages)

    # Append assistant reply to message history
    updated_messages = state["messages"] + [{"role": "assistant", "content": reply.content}]

    return {"messages": updated_messages}


# Initialize the Graph 
graph_builder = StateGraph(State)

# Register the Node in the Graph

graph_builder.add_node("classifier", classifyMessage)
graph_builder.add_node("router", router)
graph_builder.add_node("emotionalAgent", emotionalAgent)
graph_builder.add_node("logicalAgent", logicalAgent)

# in order for our graph to work, we always have to start and an end node
# Add Edges (Flow)
graph_builder.add_edge(START, "classifier")
graph_builder.add_edge("classifier", "router")
graph_builder.add_conditional_edges(
    "router",
    lambda state: state.get("next"),
    {"logicalAgent": "logicalAgent", "emotionalAgent": "emotionalAgent"}
    # means : if the next returns logicalAgent, we are letting logicalAgent Node to handle the request 
)
graph_builder.add_edge("emotionalAgent", END)
graph_builder.add_edge("logicalAgent", END)

graph = graph_builder.compile()


def run_assistant():
  state = {"messages" : [], "message_type" : None}

  while True:
    user_input = input("Your message : ")
    if user_input == "exit":
      print("Bye!")
      break

    # Append new user message
    # state["messages"].append({"role": "user", "content": user_input})


    state["messages"] = state.get("messages" , []) + [{
      "role" : "user",
      "content" : user_input
    }]

    # Invoke the graph with full message history
    state = graph.invoke(state)

    if state.get("messages") and len(state["messages"]) > 0:
      last_message = state["messages"][-1]
      print(f"Assistant : {last_message.content}")


if __name__ == "__main__":
  run_assistant()