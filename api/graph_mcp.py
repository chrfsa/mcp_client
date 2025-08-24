from mcp_client import MCPClientLangChain
config_server = {
    "deepwiki" : {
        "url" : "https://mcp.deepwiki.com/sse",
        "transport" : "sse"
    }
}

client = MCPClientLangChain(config_server)
agent = client.create_graph()
