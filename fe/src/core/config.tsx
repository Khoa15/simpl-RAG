export const config = {
    apiUrl: 'http://localhost:8000/api',
    websocketUrl: 'ws://localhost:3000/ws',
    defaultModel: 'gpt-3.5-turbo',
    defaultEmbeddingModel: 'text-embedding-3-small',
    defaultVectorStore: 'local',
    defaultChunkSize: 1000,
    defaultChunkOverlap: 200,
    defaultMaxTokens: 1000,
    defaultTemperature: 0.7,
    defaultTopP: 1.0,
}