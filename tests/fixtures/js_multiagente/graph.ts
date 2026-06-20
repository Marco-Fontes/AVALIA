// Fixture (TEXTO INERTE — nunca executada, RNF-05): sistema multiagente RAG em TypeScript,
// no estilo LangGraph.js, com defeitos por construção: loop sem teto, sem retry, sem fallback.
import { StateGraph } from "@langchain/langgraph";

interface PipelineState {
  query: string;
  context: string[];
}

const RETRIEVER_PROMPT = "You are the retriever. Retrieve documents and cite each source.";
const ANSWER_PROMPT = "Answer using only the retrieved context, with citations of the sources.";

async function retrieverAgent(state: PipelineState) {
  while (true) {
    state = await fetchMore(state); // loop sem teto (potencialmente infinito)
  }
}

const answerAgent = async (state: PipelineState) => {
  try {
    return await llm.invoke({
      model: "claude-opus-4",
      system: ANSWER_PROMPT,
      maxTokens: 1024,
      timeout: 30,
    });
  } catch (e) {
    return null;
  }
};

function build(graph: StateGraph) {
  graph.addEdge("retriever", "answerer");
  graph.addConditionalEdges("answerer", route);
}
