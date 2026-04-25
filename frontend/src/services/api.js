import axios from 'axios'

const client = axios.create({ baseURL: '/', timeout: 20000 })

export async function consult(payload) {
  const res = await client.post('/consult', payload)
  return res.data
}
