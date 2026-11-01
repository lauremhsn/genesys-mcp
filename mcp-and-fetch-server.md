# MCP and the Fetch MCP Server

Before MCP you had to write a separate integration for every model and tool
pair, each one with its own auth and data format. The article describes MCP as
turning that N×M problem into N+M. Every tool gets wrapped in one server, every
model brings one client, and then anything can talk to anything. The quote from
Anthropic about models being "trapped behind information silos" is basically the
reason it exists.

There are three roles, which the article shows in its architecture diagrams. The
host is the app the user is actually using, like Claude Desktop, or in my case
the agent script I wrote. The client sits inside the host and connects to one
server each, so a host using three servers is running three clients. The server
is the process that exposes things: tools the model can call, resources it can
read, and prompt templates. The part I found most useful is dynamic discovery,
where the client asks the server what it has at runtime instead of it being
hardcoded. That means adding a new server doesn't mean editing the agent. The
article also makes the point that LangChain standardized tools for the developer
writing the agent code, while MCP standardizes them for the model itself while
it's running. And MCP is only the Action part of an agent. It says how a tool
gets called, not when or why. That's still the planner's job.

The limitation that stuck with me is that giving a model more tools doesn't mean
it will use them well, and that this depends on how good the tool descriptions
are. The Fetch server is a good thing to check that against. It has exactly one
tool, `fetch`, which takes a URL plus `max_length`, `start_index` and `raw`.
There's also a prompt template with the same name, and no resources. For single
purpose it's about as clean as it gets. One job, typed arguments, defaults that
make sense. Two things I'd question though. The `raw` flag means the tool
fetches a page and converts it to markdown, except when it doesn't, which is the
kind of "and" we were told to watch for. The bigger one is that the behaviour
changes based on who called it. robots.txt is respected when the model calls the
tool but not when the request comes from the prompt, and the User-Agent is
different too. None of that is in the tool description, so the same call can do
two different things and the model has no way of knowing which. That seems like
the opposite of what the protocol is for.