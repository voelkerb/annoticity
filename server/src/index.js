import { createApp } from "./app.js";
import { config } from "./config.js";

const host = config.host ?? (config.publicMode ? "127.0.0.1" : undefined);
createApp().listen(config.port, host, () => console.log(`Annoticity API listening on ${host ?? "all interfaces"}:${config.port}`));
