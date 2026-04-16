import axios from "axios";

const BASE_URL = "http://localhost:5000";


export async function startTask(query, sessionId = null, yearFrom = null, yearTo = null) {
  const payload = { query };

  if (sessionId) {
    payload.session_id = sessionId;   // ← key fix: always send it
  }

  if (yearFrom) {
    payload.year_from = parseInt(yearFrom);
  }

  if (yearTo) {
    payload.year_to = parseInt(yearTo);
  }

  return axios.post(`${BASE_URL}/api/task`, payload);
}

export async function getTaskStatus(taskId) {
  return axios.get(`${BASE_URL}/api/task/${taskId}`);
}

export async function getTaskResult(taskId) {
  return axios.get(`${BASE_URL}/api/task/${taskId}/result`);
}