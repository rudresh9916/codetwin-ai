package com.shopverse.admin;

import org.springframework.web.bind.annotation.*;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final ReportService reportService;

    public AdminController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/dashboard")
    public Map<String, Object> dashboard() {
        return reportService.dashboard();
    }

    @GetMapping("/reports/sales")
    public List<Map<String, Object>> sales(@RequestParam String from, @RequestParam String to) {
        return reportService.salesByCategory(from, to);
    }

    @GetMapping("/reports/legacy-export")
    public String legacyExport() {
        return "deprecated";
    }
}
