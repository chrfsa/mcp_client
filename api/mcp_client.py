from typing import Optional, TypedDict
from contextlib import AsyncExitStack
import traceback

# from utils.logger import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from datetime import datetime
from utils.logger import logger
import json
import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv
load_dotenv()
class MCPClientLangChain():
    def __init__(self, config_server : TypedDict):
        self.config_server = config_server
        self.client = MultiServerMCPClient(self.config_server)
        self.tools = []
        self.llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
    async def get_mcp_tools(self):
        tools = await self.client.get_tools()
        self.tools = tools
        return tools
    
    async def stream_query(self, query: str):
        if not self.tools:
            await self.get_mcp_tools()
        agent = create_react_agent(self.llm, tools=self.tools)
        response = await agent.ainvoke({"messages": query})
        return response


# config_server = {
#     "deepwiki" : {
#         "url" : "https://mcp.deepwiki.com/sse",
#         "transport" : "sse"
#     }
# }








# import asyncio

# async def main():
#     client = MCPClientLangChain(config_server)
#     OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
#     response = await client.stream_query("use the tool and tell me what is the main fonction in langchain and what means runnable")
#     print(response)

# # Exécuter la fonction async
# asyncio.run(main())




class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.llm = OpenAI()
        self.tools = []
        self.messages = []
        self.logger = logger

    # connect to the MCP server
    async def connect_to_server(self, server_script_path: str):
        try:
            is_python = server_script_path.endswith(".py")
            is_js = server_script_path.endswith(".js")
            if not (is_python or is_js):
                raise ValueError("Server script must be a .py or .js file")

            command = "python3" if is_python else "node"
            server_params = StdioServerParameters(
                command=command, args=[server_script_path], env=None
            )

            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.stdio, self.write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.stdio, self.write)
            )

            await self.session.initialize()

            self.logger.info("Connected to MCP server")

            mcp_tools = await self.get_mcp_tools()
            self.tools = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                
                } for tool in mcp_tools
            ]



            self.logger.info(
                f"Available tools: {[tool['name'] for tool in self.tools]}"
            )



            return True

        except Exception as e:
            self.logger.error(f"Error connecting to MCP server: {e}")
            traceback.print_exc()
            raise

    # get mcp tool list
    async def get_mcp_tools(self):
        try:
            response = await self.session.list_tools()
            return response.tools
        except Exception as e:
            self.logger.error(f"Error getting MCP tools: {e}")
            raise

    # process query
   

    async def process_query(self, query: str):
        try:
            self.logger.info(f"Processing query: {query}")
            # Crée le message utilisateur initial
            user_message = {"role": "user", "content": query}
            self.messages = [user_message]

            while True:
                # Appel LLM OpenAI
                response = await self.call_llm()

                # Récupérer le texte final de la réponse (extrait output_text)
                assistant_text = ""
                for msg in response.output:
                    if hasattr(msg, "content"):
                        for c in msg.content:
                            if getattr(c, "type", None) == "output_text":
                                assistant_text += c.text + "\n"

                # Ajouter la réponse assistant
                assistant_message = {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": assistant_text.strip()}]
                }
                self.messages.append(assistant_message)
                await self.log_conversation()

                # Vérifier s'il y a des tool calls
                function_calls = [x for x in response.output if getattr(x, "type", None) == "function_call"]
                if not function_calls:
                    break  # plus de tool, on a fini

                # Exécuter les tool calls
                for item in function_calls:
                    tool_name = item.name
                    tool_args = json.loads(item.arguments)
                    self.logger.info(f"Calling tool {tool_name} with args {tool_args}")

                    # Appel du tool (async)
                    result_output = await self.session.call_tool(tool_name, tool_args)

                    # Extraire le texte réel du résultat
                    tool_text = ""
                    if hasattr(result_output, "content"):
                        for c in result_output.content:
                            if hasattr(c, "text"):
                                tool_text += c.text + "\n"
                    else:
                        tool_text = str(result_output)

                    # Ajouter le résultat comme message utilisateur pour LLM
                    self.messages.append({
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": f"Résultat du tool {tool_name}: {tool_text.strip()}"}
                        ]
                    })
                    await self.log_conversation()

            # Retourne la conversation complète
            return self.messages

        except Exception as e:
            self.logger.error(f"Error processing query: {e}")
            raise


    # Appel au LLM
    async def call_llm(self):
        try:
            self.logger.info("Calling LLM")
            return self.llm.responses.create(
                model="gpt-4.1",
                input=self.messages,
                tools=self.tools
            )
        except Exception as e:
            self.logger.error(f"Error calling LLM: {e}")
            raise


    # cleanup
    async def cleanup(self):
        try:
            await self.exit_stack.aclose()
            self.logger.info("Disconnected from MCP server")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            traceback.print_exc()
            raise

    async def log_conversation(self):
        os.makedirs("conversations", exist_ok=True)

        serializable_conversation = []

        for message in self.messages:
            try:
                serializable_message = {"role": message["role"], "content": []}

                # Handle both string and list content
                if isinstance(message["content"], str):
                    serializable_message["content"] = message["content"]
                elif isinstance(message["content"], list):
                    for content_item in message["content"]:
                        if hasattr(content_item, "to_dict"):
                            serializable_message["content"].append(
                                content_item.to_dict()
                            )
                        elif hasattr(content_item, "dict"):
                            serializable_message["content"].append(content_item.dict())
                        elif hasattr(content_item, "model_dump"):
                            serializable_message["content"].append(
                                content_item.model_dump()
                            )
                        else:
                            serializable_message["content"].append(content_item)

                serializable_conversation.append(serializable_message)
            except Exception as e:
                self.logger.error(f"Error processing message: {str(e)}")
                self.logger.debug(f"Message content: {message}")
                raise

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join("conversations", f"conversation_{timestamp}.json")

        try:
            with open(filepath, "w") as f:
                json.dump(serializable_conversation, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error writing conversation to file: {str(e)}")
            self.logger.debug(f"Serializable conversation: {serializable_conversation}")
            raise



