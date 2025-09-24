/**
 * Simple test script to verify chat API error handling fixes
 */

// Mock fetch for testing
const originalFetch = global.fetch;

// Test the improved error handling
async function testErrorHandling() {
    console.log('Testing chat API error handling...');
    
    // Import the ChatAPI class
    const ChatAPI = require('./lib/chat-api.ts').default;
    
    // Create a test instance
    const chatAPI = new ChatAPI('test-token');
    
    // Mock fetch to return different error scenarios
    global.fetch = jest.fn()
        .mockResolvedValueOnce({
            ok: false,
            status: 500,
            json: () => Promise.resolve({ error: 'Internal server error' })
        })
        .mockResolvedValueOnce({
            ok: false,
            status: 401,
            json: () => Promise.resolve({ detail: 'Authentication required' })
        })
        .mockResolvedValueOnce({
            ok: false,
            status: 400,
            json: () => Promise.resolve({ message: 'Bad request' })
        })
        .mockResolvedValueOnce({
            ok: false,
            status: 503,
            json: () => Promise.resolve({ error: { code: 'SERVICE_UNAVAILABLE', details: 'Redis timeout' } })
        });
    
    const testCases = [
        { name: 'String error', expectedMessage: 'Internal server error' },
        { name: 'Detail error', expectedMessage: 'Authentication required' },
        { name: 'Message error', expectedMessage: 'Bad request' },
        { name: 'Object error', expectedMessage: '{"code":"SERVICE_UNAVAILABLE","details":"Redis timeout"}' }
    ];
    
    for (let i = 0; i < testCases.length; i++) {
        const testCase = testCases[i];
        try {
            await chatAPI.createSession({ title: 'Test' });
            console.log(`❌ ${testCase.name}: Expected error but got success`);
        } catch (error) {
            if (error.message.includes(testCase.expectedMessage)) {
                console.log(`✅ ${testCase.name}: Error handled correctly`);
            } else {
                console.log(`❌ ${testCase.name}: Expected "${testCase.expectedMessage}" but got "${error.message}"`);
            }
        }
    }
    
    // Restore original fetch
    global.fetch = originalFetch;
}

// Run the test if this file is executed directly
if (require.main === module) {
    testErrorHandling().catch(console.error);
}

module.exports = { testErrorHandling };