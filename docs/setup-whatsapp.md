# WhatsApp setup

The local demo uses the phone simulator with all WhatsApp credentials blank. Run the owner console on loopback, load the Kirana demo and select **Try it (phone)**. The same agent handles simulator messages and authenticated WhatsApp callbacks.

## Optional Meta test number

1. Use the WhatsApp API Setup panel in your Meta developer app. Select the test number and verify the teammate phones you want to use. Each person messages the test number from their own WhatsApp. [Meta setup](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)
2. Enter the test phone number ID in `WA_PHONE_NUMBER_ID`, the temporary access token in `WA_TOKEN` and the app secret in `WA_APP_SECRET` in the local ignored `.env`. Choose your own `WA_VERIFY_TOKEN`. The app secret authenticates each inbound callback.
3. Set the owner phone and contact roles in the local console. A message from each test phone opens its own 24-hour service window. Bolo records out-of-window sends in the console. [WhatsApp pricing](https://business.whatsapp.com/products/platform-pricing)
4. Run the two processes below from `backend/` with the same virtual environment and `BOLO_DATA_DIR`. Configure the tunnel for port **8001**. The owner console on **8000** manages people, money and approvals and belongs on loopback.

```powershell
# Terminal 1
python -m uvicorn app:app --host 127.0.0.1 --port 8000

# Terminal 2
python -m uvicorn gateway:app --host 127.0.0.1 --port 8001

# Terminal 3
cloudflared tunnel --url http://127.0.0.1:8001
```

Set `PUBLIC_BASE_URL` to the resulting HTTPS URL and restart both Python processes. Enter `<PUBLIC_BASE_URL>/webhook` as the callback with the same verify token and subscribe to `messages`. Update the URL after each tunnel restart.

Send a text, then a short voice note. Test a reply button and approve a quotation for another opted-in test phone. Meta uploads mono OGG/Opus voice notes and PDFs using its media endpoint. Provider acceptance and physical handset delivery are separate observations. [Meta voice message example](https://www.postman.com/meta/whatsapp-business-platform/request/goznbg0/send-audio-message-by-id)

## Existing Twilio sandbox support

Keep the Twilio keys blank for the free-only build. Twilio documents standard sandbox message charges and a limited trial allowance. [Twilio sandbox terms](https://www.twilio.com/docs/whatsapp/sandbox)

For a team already using a sandbox, its callback is `<PUBLIC_BASE_URL>/twilio` using POST. `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM` and `PUBLIC_BASE_URL` identify the account, validate signatures and send replies. Each phone must join the sandbox. Reply buttons become numbered choices. Voice and PDF attachments use expiring links scoped to one file.

## Offline regression test

From `backend/`, run `python -m unittest -v tests.test_transport`. The tests exercise signed Meta and Twilio requests, duplicate delivery, numbered and native buttons, incoming audio bytes, outbound OGG/Opus, PDF attachments, service windows and partial failures with synthetic phones and local HTTP fixtures. For a live test, verify receipt on both participating handsets.

Inbound IDs persist across restarts. Bolo retries media retrieval before handing a message to the agent. When a shop action fails after it begins, Activity records `webhook_needs_review`. The owner can inspect the conversation and ledger before deciding whether any work remains.
